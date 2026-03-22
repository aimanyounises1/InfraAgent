"""Platform auto-detection — discovers available infrastructure at startup.

Probes the real runtime environment and reports what subsystems are available:
- GPU: NVIDIA (pynvml/DCGM), Apple Silicon (Metal via psutil), or none
- Orchestrator: Kubernetes (via kubeconfig), Slurm (via scontrol), or none
- Incident tools: Jira, Grafana, PagerDuty (via reachability checks)

Every MCP tool reads from this module to decide whether to query real
hardware or report "subsystem not available" — never fake data.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Capability dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GpuCapability:
    """Detected GPU subsystem."""

    available: bool = False
    backend: str = "none"  # "nvml", "apple_metal", "none"
    device_count: int = 0
    driver_version: str = ""
    gpu_names: tuple[str, ...] = ()
    dcgm_available: bool = False
    dcgm_version: str = ""
    nvlink_present: bool = False


@dataclass(frozen=True)
class OrchestratorCapability:
    """Detected cluster orchestrator."""

    kubernetes: bool = False
    k8s_context: str = ""
    k8s_version: str = ""
    slurm: bool = False
    slurm_version: str = ""
    slurm_cluster: str = ""


@dataclass(frozen=True)
class IncidentCapability:
    """Detected incident management tools."""

    jira_reachable: bool = False
    grafana_reachable: bool = False
    pagerduty_reachable: bool = False


@dataclass(frozen=True)
class PlatformInfo:
    """Complete platform detection result."""

    os_name: str = ""  # "Linux", "Darwin", "Windows"
    os_version: str = ""
    arch: str = ""  # "x86_64", "arm64"
    hostname: str = ""
    python_version: str = ""
    gpu: GpuCapability = field(default_factory=GpuCapability)
    orchestrator: OrchestratorCapability = field(default_factory=OrchestratorCapability)
    incidents: IncidentCapability = field(default_factory=IncidentCapability)


# ---------------------------------------------------------------------------
# GPU Detection
# ---------------------------------------------------------------------------


def _detect_nvidia_gpu() -> GpuCapability | None:
    """Try to detect NVIDIA GPUs via pynvml."""
    try:
        import pynvml

        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()
        if count == 0:
            pynvml.nvmlShutdown()
            return None

        driver = pynvml.nvmlSystemGetDriverVersion()
        if isinstance(driver, bytes):
            driver = driver.decode("utf-8")

        names: list[str] = []
        nvlink_present = False
        for i in range(count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode("utf-8")
            names.append(name)

            # Check NVLink presence
            try:
                for link in range(18):  # H100 has up to 18 links
                    state = pynvml.nvmlDeviceGetNvLinkState(handle, link)
                    if state:
                        nvlink_present = True
                        break
            except Exception:
                pass

        # Check DCGM availability
        dcgm_available = False
        dcgm_version = ""
        try:
            import pydcgm  # noqa: F401

            dcgm_available = True
            try:
                dcgm_version = pydcgm.dcgm_structs.dcgmVersionInfo_t().version
            except Exception:
                dcgm_version = "available"
        except ImportError:
            # Also check if dcgmi CLI is available
            if shutil.which("dcgmi"):
                dcgm_available = True
                try:
                    result = subprocess.run(
                        ["dcgmi", "version"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    dcgm_version = result.stdout.strip().split("\n")[0] if result.returncode == 0 else "cli-only"
                except Exception:
                    dcgm_version = "cli-only"

        return GpuCapability(
            available=True,
            backend="nvml",
            device_count=count,
            driver_version=driver,
            gpu_names=tuple(names),
            dcgm_available=dcgm_available,
            dcgm_version=dcgm_version,
            nvlink_present=nvlink_present,
        )
    except ImportError:
        logger.debug("pynvml not installed — NVIDIA GPU detection skipped")
        return None
    except Exception as exc:
        logger.debug("NVIDIA GPU detection failed: %s", exc)
        return None


def _detect_apple_gpu() -> GpuCapability | None:
    """Detect Apple Silicon GPU via system profiler."""
    if platform.system() != "Darwin":
        return None

    try:
        import psutil

        # Check if running on Apple Silicon
        machine = platform.machine()
        if machine not in ("arm64", "aarch64"):
            return None

        # Get chip name from sysctl
        chip_name = "Apple Silicon"
        try:
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                chip_name = result.stdout.strip()
        except Exception:
            pass

        # Get GPU core count
        gpu_cores = 0
        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType", "-json"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                import json

                data = json.loads(result.stdout)
                displays = data.get("SPDisplaysDataType", [])
                if displays:
                    gpu_cores = displays[0].get("sppci_cores", 0)
        except Exception:
            pass

        gpu_name = chip_name
        if gpu_cores:
            gpu_name = f"{chip_name} ({gpu_cores}-core GPU)"

        return GpuCapability(
            available=True,
            backend="apple_metal",
            device_count=1,  # Unified GPU
            driver_version=f"macOS {platform.mac_ver()[0]}",
            gpu_names=(gpu_name,),
            dcgm_available=False,
            nvlink_present=False,
        )
    except ImportError:
        return None
    except Exception as exc:
        logger.debug("Apple GPU detection failed: %s", exc)
        return None


def _detect_gpu() -> GpuCapability:
    """Detect GPU — tries NVIDIA first, then Apple, then reports none."""
    nvidia = _detect_nvidia_gpu()
    if nvidia is not None:
        return nvidia

    apple = _detect_apple_gpu()
    if apple is not None:
        return apple

    return GpuCapability()


# ---------------------------------------------------------------------------
# Orchestrator Detection
# ---------------------------------------------------------------------------


def _detect_kubernetes() -> tuple[bool, str, str]:
    """Check if Kubernetes is accessible."""
    try:
        # Check for kubeconfig
        kubeconfig = os.environ.get("KUBECONFIG", os.path.expanduser("~/.kube/config"))
        if not os.path.isfile(kubeconfig):
            # Also check in-cluster config
            if not os.path.isfile("/var/run/secrets/kubernetes.io/serviceaccount/token"):
                return False, "", ""

        kubectl = shutil.which("kubectl")
        if not kubectl:
            return False, "", ""

        # Try to get current context
        ctx_result = subprocess.run(
            ["kubectl", "config", "current-context"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        context = ctx_result.stdout.strip() if ctx_result.returncode == 0 else ""

        # Try to get server version
        ver_result = subprocess.run(
            ["kubectl", "version", "--client", "--short"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        version = ver_result.stdout.strip() if ver_result.returncode == 0 else ""

        return True, context, version
    except Exception as exc:
        logger.debug("Kubernetes detection failed: %s", exc)
        return False, "", ""


def _detect_slurm() -> tuple[bool, str, str]:
    """Check if Slurm is accessible."""
    try:
        scontrol = shutil.which("scontrol")
        if not scontrol:
            return False, "", ""

        # Get Slurm version
        ver_result = subprocess.run(
            ["scontrol", "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        version = ""
        if ver_result.returncode == 0:
            version = ver_result.stdout.strip().split("\n")[0]

        # Get cluster name
        cluster_result = subprocess.run(
            ["scontrol", "show", "config"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        cluster = ""
        if cluster_result.returncode == 0:
            for line in cluster_result.stdout.split("\n"):
                if "ClusterName" in line:
                    cluster = line.split("=", 1)[1].strip()
                    break

        return True, version, cluster
    except Exception as exc:
        logger.debug("Slurm detection failed: %s", exc)
        return False, "", ""


def _detect_orchestrator() -> OrchestratorCapability:
    """Detect Kubernetes and/or Slurm."""
    k8s_ok, k8s_ctx, k8s_ver = _detect_kubernetes()
    slurm_ok, slurm_ver, slurm_cluster = _detect_slurm()
    return OrchestratorCapability(
        kubernetes=k8s_ok,
        k8s_context=k8s_ctx,
        k8s_version=k8s_ver,
        slurm=slurm_ok,
        slurm_version=slurm_ver,
        slurm_cluster=slurm_cluster,
    )


# ---------------------------------------------------------------------------
# Incident Tools Detection
# ---------------------------------------------------------------------------


def _check_url_reachable(url: str, timeout: int = 3) -> bool:
    """Quick HTTP HEAD check."""
    if not url:
        return False
    try:
        import urllib.request

        req = urllib.request.Request(url, method="HEAD")
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except Exception:
        return False


def _detect_incidents() -> IncidentCapability:
    """Check reachability of incident tools from environment variables."""
    jira_url = os.environ.get("INFRA_AGENT_JIRA_URL", "")
    grafana_url = os.environ.get("INFRA_AGENT_GRAFANA_URL", "")
    pd_token = os.environ.get("INFRA_AGENT_PAGERDUTY_TOKEN", "")

    return IncidentCapability(
        jira_reachable=_check_url_reachable(jira_url),
        grafana_reachable=_check_url_reachable(grafana_url),
        pagerduty_reachable=bool(pd_token),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def detect_platform() -> PlatformInfo:
    """Run full platform detection — cached after first call.

    Call this at startup to discover what infrastructure is available.
    All MCP tools and agents read from the returned PlatformInfo to
    decide their behavior.
    """
    import sys

    logger.info("Running platform detection...")

    gpu = _detect_gpu()
    orchestrator = _detect_orchestrator()
    incidents = _detect_incidents()

    info = PlatformInfo(
        os_name=platform.system(),
        os_version=platform.release(),
        arch=platform.machine(),
        hostname=platform.node(),
        python_version=sys.version.split()[0],
        gpu=gpu,
        orchestrator=orchestrator,
        incidents=incidents,
    )

    logger.info(
        "Platform detected: os=%s arch=%s gpu=%s(%d devices) k8s=%s slurm=%s",
        info.os_name,
        info.arch,
        info.gpu.backend,
        info.gpu.device_count,
        info.orchestrator.kubernetes,
        info.orchestrator.slurm,
    )
    return info


def platform_summary() -> dict[str, Any]:
    """Return a JSON-serializable summary of detected capabilities."""
    p = detect_platform()
    return {
        "system": {
            "os": p.os_name,
            "os_version": p.os_version,
            "arch": p.arch,
            "hostname": p.hostname,
            "python": p.python_version,
        },
        "gpu": {
            "available": p.gpu.available,
            "backend": p.gpu.backend,
            "device_count": p.gpu.device_count,
            "driver": p.gpu.driver_version,
            "devices": list(p.gpu.gpu_names),
            "dcgm": p.gpu.dcgm_available,
            "nvlink": p.gpu.nvlink_present,
        },
        "orchestrator": {
            "kubernetes": p.orchestrator.kubernetes,
            "k8s_context": p.orchestrator.k8s_context,
            "slurm": p.orchestrator.slurm,
            "slurm_cluster": p.orchestrator.slurm_cluster,
        },
        "incidents": {
            "jira": p.incidents.jira_reachable,
            "grafana": p.incidents.grafana_reachable,
            "pagerduty": p.incidents.pagerduty_reachable,
        },
    }
