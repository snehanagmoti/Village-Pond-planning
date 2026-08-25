FROM node:24-alpine AS build
WORKDIR /app
ARG VITE_IMAGERY_TILE_URL
ARG VITE_IMAGERY_ATTRIBUTION
ENV VITE_IMAGERY_TILE_URL=${VITE_IMAGERY_TILE_URL} \
    VITE_IMAGERY_ATTRIBUTION=${VITE_IMAGERY_ATTRIBUTION}
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.28-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
