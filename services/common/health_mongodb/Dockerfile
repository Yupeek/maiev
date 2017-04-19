FROM mongo

COPY "check_mongo.sh" "/app/"
HEALTHCHECK --interval=10s --timeout=6s CMD '/app/check_mongo.sh'