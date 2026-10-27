# API evidence

Versions resolved with `uv sync --frozen --extra dev --extra ollama` and installed distribution metadata. The committed uv.lock is the dependency authority.

| symbol | package@version | source | quote |
|---|---|---|---|
| BaseSettings | pydantic-settings@2.13.1 | installed pydantic_settings/main.py, BaseSettings docstring | "Base class for settings, allowing values to be overridden by environment variables." |
| env_prefix | pydantic-settings@2.13.1 | installed pydantic_settings/main.py, BaseSettings docstring; Context7 /pydantic/pydantic-settings query BaseSettings env_prefix bool fields | "_env_prefix: Prefix for all environment variables. Defaults to `None`." |
| FastMCP.tool | mcp@1.26.0 | installed mcp/server/fastmcp/server.py | "Decorator to register a tool."; decorator calls `self.add_tool(fn, ...)` and `return fn` |
| FastMCP.call_tool | mcp@1.26.0 | installed mcp/server/fastmcp/server.py | "Call a tool by name with arguments." |
| StructuredTool.ainvoke | langchain-core@1.2.20 | installed langchain_core/tools/structured.py | `input: str \| dict \| ToolCall` and `return await super().ainvoke(input, config, **kwargs)` |
| json.dumps / json.loads | Python@3.14.0 | https://docs.python.org/3.14/library/json.html | "Serialize obj to a JSON formatted str using this conversion table."; "Deserialize s (a str, bytes or bytearray instance containing a JSON document) to a Python object" |
| logging.getLogger / Logger.warning | Python@3.14.0 | https://docs.python.org/3.14/library/logging.html | "Loggers should NEVER be instantiated directly, but always through the module-level function logging.getLogger(name)."; "Logs a message with level WARNING on this logger." |
| pytest.fixture / mark.usefixtures | pytest@9.0.2 | installed _pytest/fixtures.py, fixture docstring | "Decorator to mark a fixture factory function."; "test modules or classes can use the ``pytest.mark.usefixtures(fixturename)`` marker." |
| pytest.mark.parametrize | pytest@9.0.2 | installed _pytest/python.py, Metafunc.parametrize docstring | "Add new invocations to the underlying test function using the list of argvalues for the given argnames." |
| MonkeyPatch.setenv / delenv | pytest@9.0.2 | installed _pytest/monkeypatch.py | "Set environment variable ``name`` to ``value``."; "Delete ``name`` from the environment." |
| unittest.mock.patch / patch.object | Python@3.14.0 | installed unittest/mock.py | "Inside the body of the function or with statement, the `target` is patched with a `new` object."; "patch the named member (`attribute`) on an object (`target`) with a mock object." |
| MagicMock / AsyncMock | Python@3.14.0 | installed unittest/mock.py | "MagicMock is a subclass of Mock with default implementations of most of the magic methods."; "Enhance :class:`Mock` with features allowing to mock an async function." |
| ExitStack | Python@3.14.0 | installed contextlib.py | "Context manager for dynamic management of a stack of exit callbacks." |
| importlib.import_module | Python@3.14.0 | installed importlib/__init__.py | "Import a module." |
| AIMessage / HumanMessage / ToolMessage | langchain-core@1.2.20 | installed langchain_core/messages/{ai,human,tool}.py | "Message from an AI."; "Message from a human."; "Message for passing the result of executing a tool back to a model." |
| StateGraph Pydantic node state | langgraph@1.1.3 | installed langgraph/graph/state.py, _pick_mapper / _coerce_state; https://docs.langchain.com/oss/python/langgraph/use-graph-api | `return partial(_coerce_state, schema)`; `return schema(**input)`; official guide: "Nodes receive validated Pydantic objects, but graph outputs are dictionaries." |
| py-modules | setuptools@84.2.1 | wheel WHEEL generator metadata; https://setuptools.pypa.io/en/stable/userguide/pyproject_config.html | "When both `py-modules` and `packages` are left unspecified, `setuptools` will attempt to perform Automatic discovery" |
| checkout | actions/checkout@v4 | fetched https://raw.githubusercontent.com/actions/checkout/v4/README.md | `uses: actions/checkout@v4` |
| setup-python python-version | actions/setup-python@v5 | fetched https://raw.githubusercontent.com/actions/setup-python/v5/README.md | `uses: actions/setup-python@v5`; `python-version: '3.13'` |
| setup-node cache / node-version | actions/setup-node@v4 | fetched https://raw.githubusercontent.com/actions/setup-node/v4/README.md | "File containing the version Spec of the version to use."; `node-version: 18`; `run: npm ci` |
| setup-uv version | astral-sh/setup-uv@v6 | fetched https://raw.githubusercontent.com/astral-sh/setup-uv/v6/README.md | `uses: astral-sh/setup-uv@v6`; "Install a specific version" |
| uv sync --frozen / uv build --wheel | uv@0.9.11 | installed `uv sync --help`, `uv build --help`; https://docs.astral.sh/uv/reference/cli/ | "Sync without updating the `uv.lock` file"; "Build a Python wheel" |

The wheel smoke check initially resolved MCP 2.x through the undeclared transitive dependency and failed to import `mcp.server.fastmcp`. This repository uses the MCP 1.x API above, so `mcp>=1.26,<2` is now an explicit dependency. The frozen environment remains on 1.26.0; the separate unconstrained wheel-install smoke resolved MCP 1.30.0 successfully. No dependency versions in uv.lock were upgraded.

| typing.get_type_hints | Python@3.14.0 | installed typing.py | "Return type hints for an object." |
