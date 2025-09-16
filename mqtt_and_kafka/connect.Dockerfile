# Base image for Kafka Connect
FROM confluentinc/cp-kafka-connect:7.6.1

# Switch to root to allow installation and file copying
USER root

# Define target directory for custom plugins (location within the container)
ENV CUSTOM_PLUGINS=/usr/share/confluent-hub-components

# Ensure the plugins directory exists
RUN mkdir -p ${CUSTOM_PLUGINS}

# Copy the entire plugin directory (including lib) into the image
# The directory within the image will be "confluentinc-kafka-connect-mqtt"
COPY connect/plugins/confluentinc-kafka-connect-mqtt-1.7.6 \
     ${CUSTOM_PLUGINS}/confluentinc-kafka-connect-mqtt

# Set the plugin path environment variable to include the default path plus our custom plugin path
ENV CONNECT_PLUGIN_PATH="/usr/share/java,${CUSTOM_PLUGINS}"

# Switch back to the default non-root user for security
USER appuser

# Expose the default Kafka Connect port
EXPOSE 8083
