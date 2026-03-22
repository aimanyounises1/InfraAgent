# InfraAgent — React dashboard
FROM node:20-slim AS build

WORKDIR /app
COPY package.json .
RUN npm install
COPY . .
RUN npm run build

# Serve with lightweight static server
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]
