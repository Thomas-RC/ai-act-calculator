FROM nginx:1.27-alpine

# Podmieniamy default config
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/app.conf

# Statyka frontendu
COPY index.html /usr/share/nginx/html/index.html
COPY assets /usr/share/nginx/html/assets
COPY partials /usr/share/nginx/html/partials

EXPOSE 8080

# Healthcheck — sprawdza że nginx oddaje index
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD wget -qO- http://127.0.0.1:8080/ > /dev/null || exit 1
