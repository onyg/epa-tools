FROM mcr.microsoft.com/devcontainers/base:alpine-3.20

# Setzen der Umgebungsvariablen
ENV FIRELY_TERMINAL_VERSION=3.3.2
ENV JAVA_VALIDATOR_VERSION=6.3.18
ENV SUSHI_VERSION=3.15.0

# Installieren der notwendige Tools
# Add Microsoft's .NET SDK repository and install .NET SDK
RUN apk add --no-cache dotnet8-sdk

# Install ICU libraries
RUN apk add --no-cache icu-libs

# Install Node.js and npm
RUN apk add --no-cache nodejs npm

# Install Java (OpenJDK)
RUN apk add --no-cache openjdk11

# Install jekyll
RUN apk add --no-cache jekyll

# Install py-pip
RUN apk add --no-cache py-pip py3-yaml pipx

# Install Firely Terminal as vscode user
# Switch to the vscode user
USER vscode

# Install Firely Terminal
RUN dotnet tool install --global Firely.Terminal --version $FIRELY_TERMINAL_VERSION

# Add .NET tools to PATH for vscode user
ENV PATH="/home/vscode/.dotnet/tools:${PATH}"

# Switch back to root user to perform remaining installations
USER root

RUN npm install -g fsh-sushi@$SUSHI_VERSION

# Static webserver for local development
RUN npm install -g http-server

# Installieren der zusätzliche Abhängigkeiten
RUN apk update && apk add --no-cache jq findutils curl ca-certificates

# Setup for FHIR Validator
RUN mkdir -p /home/vscode/.fhir/validators/
RUN wget -q https://github.com/hapifhir/org.hl7.fhir.core/releases/download/$JAVA_VALIDATOR_VERSION/validator_cli.jar -O /home/vscode/.fhir/validators/validator_cli.jar

# Set ownership
RUN mkdir -p /home/vscode/.fhir/packages && \
  chown -R vscode:vscode /home/vscode/.fhir/packages

RUN mkdir -p /home/vscode/.fhir/settings/
COPY codfsh-config.yaml /home/vscode/.fhir/settings/codfsh-config.yaml

# Installing PlantUML...
RUN apk add curl graphviz fontconfig

# Setzen des Arbeitsverzeichnis
WORKDIR /workspace

COPY . /workspace

CMD [ "/bin/bash" ]
