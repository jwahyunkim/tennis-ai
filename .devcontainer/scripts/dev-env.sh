#!/usr/bin/env sh

# Shared by login shells, interactive terminals, and development setup scripts.
export FLUTTER_HOME=/opt/flutter
export ANDROID_HOME=/opt/android-sdk
export ANDROID_SDK_ROOT=/opt/android-sdk
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH="/home/codespace/.local/bin:${JAVA_HOME}/bin:${FLUTTER_HOME}/bin:${FLUTTER_HOME}/bin/cache/dart-sdk/bin:${ANDROID_HOME}/cmdline-tools/latest/bin:${ANDROID_HOME}/platform-tools:${PATH}"
