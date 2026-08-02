FROM mcr.microsoft.com/devcontainers/universal:2-linux

ARG DEBIAN_FRONTEND=noninteractive
ARG FLUTTER_VERSION=3.44.7
ARG ANDROID_COMMAND_LINE_TOOLS_VERSION=15859902
ARG CODEX_VERSION=0.146.0

ENV FLUTTER_HOME=/opt/flutter \
    ANDROID_HOME=/opt/android-sdk \
    ANDROID_SDK_ROOT=/opt/android-sdk \
    JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64

ENV PATH=${JAVA_HOME}/bin:${FLUTTER_HOME}/bin:${FLUTTER_HOME}/bin/cache/dart-sdk/bin:${ANDROID_HOME}/cmdline-tools/latest/bin:${ANDROID_HOME}/platform-tools:${PATH}

USER root

RUN apt-get update \
    && apt-get install -y \
        curl \
        git \
        unzip \
        xz-utils \
        zip \
        openjdk-17-jdk \
        libglu1-mesa \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL \
        "https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_${FLUTTER_VERSION}-stable.tar.xz" \
        -o /tmp/flutter.tar.xz \
    && tar -xf /tmp/flutter.tar.xz -C /opt \
    && rm /tmp/flutter.tar.xz \
    && chown -R codespace:codespace ${FLUTTER_HOME}

RUN mkdir -p ${ANDROID_HOME}/cmdline-tools \
    && curl -fsSL \
        "https://dl.google.com/android/repository/commandlinetools-linux-${ANDROID_COMMAND_LINE_TOOLS_VERSION}_latest.zip" \
        -o /tmp/android-command-line-tools.zip \
    && unzip -q /tmp/android-command-line-tools.zip -d /tmp/android-command-line-tools \
    && mv /tmp/android-command-line-tools/cmdline-tools ${ANDROID_HOME}/cmdline-tools/latest \
    && rm -rf /tmp/android-command-line-tools \
    && rm /tmp/android-command-line-tools.zip

RUN yes | sdkmanager --licenses \
    && sdkmanager \
        "platform-tools" \
        "platforms;android-36" \
        "build-tools;36.0.0" \
    && chown -R codespace:codespace ${ANDROID_HOME}

USER codespace

RUN git config --global --add safe.directory ${FLUTTER_HOME} \
    && flutter config --no-analytics \
    && flutter config --enable-web \
    && flutter config --android-sdk ${ANDROID_HOME} \
    && flutter precache --web --android

# Install the official OpenAI Codex CLI for the Codespaces user.
USER codespace

RUN curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_RELEASE=${CODEX_VERSION} CODEX_NON_INTERACTIVE=1 sh \
    && /home/codespace/.local/bin/codex --version

ENV PATH=/home/codespace/.local/bin:${PATH}
