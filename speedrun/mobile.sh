#!/usr/bin/env bash
# Speedrun mobile helper: boot the Android emulator, install our AnkiDroid
# full-debug build, and push the AMC deck. Run from your own Terminal (a GUI
# session) so the emulator window can open:
#
#     bash speedrun/mobile.sh
#
# Then in the emulator: tap "Get started", and import the pushed deck
# (Files -> Download -> amc_10a_2022.apkg, or AnkiDroid -> Import).
set -euo pipefail

export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@17}"
export ANDROID_HOME="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"

REPO="$(cd "$(dirname "$0")/.." && pwd)"
APK="$REPO/speedrun/out/Anki-Android/AnkiDroid/build/outputs/apk/full/debug/AnkiDroid-full-arm64-v8a-debug.apk"
AVD="${AVD:-speedrun}"

[ -f "$APK" ] || { echo "APK not found: $APK
Build it first: (cd speedrun/out/Anki-Android && ./gradlew :AnkiDroid:assembleFullDebug)"; exit 1; }

if ! adb devices | grep -q "emulator-.*device"; then
  echo "Booting emulator '$AVD' (a window should appear)..."
  emulator -avd "$AVD" -no-boot-anim >/tmp/speedrun-emulator.log 2>&1 &
fi

echo "Waiting for device..."
adb wait-for-device
until [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; do sleep 3; done
echo "Booted."

adb install -r -t "$APK"

echo "Pushing decks to /sdcard/Download ..."
adb shell mkdir -p /sdcard/Download >/dev/null 2>&1 || true
pushed=0
for f in "$REPO"/speedrun/decks/*.apkg "$REPO"/speedrun/out/amc_10a_2022.apkg; do
  [ -f "$f" ] || continue
  if adb push "$f" "/sdcard/Download/$(basename "$f")" >/dev/null 2>&1; then
    echo "  + $(basename "$f")"
    pushed=$((pushed + 1))
  fi
done
echo "Pushed $pushed deck file(s)."

cat <<'EOF'

Ready. In the emulator:
  1. Open AnkiDroid, tap "Get started" (you can skip AnkiWeb sync).
  2. Import a deck: tap the top-right overflow menu (three dots) -> "Import",
     (or open Files -> Download and tap an .apkg), pick a file such as
     AMC_10A.apkg, then choose "Add". Repeat for each deck you want.
  3. Open e.g. "Speedrun::AMC 10A" -> Study. The multiple-choice cards are
     interactive: tap a choice to reveal the worked solution + correct answer.

Note: topic interleaving / topic-aware scheduling are NOT active on mobile yet
(that is M2 - building our Rust backend for Android, deferred). The deck and the
interactive MC cards work on the stock engine.
EOF
