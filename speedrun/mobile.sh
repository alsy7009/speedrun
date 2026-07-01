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

# `--reset` wipes AnkiDroid's collection so the new tier decks (AMC 8 / 10 / 12)
# import from a clean state — use this to clear leftover old-structure decks.
if [ "${1:-}" = "--reset" ] || [ "${RESET:-}" = "1" ]; then
  echo "Resetting AnkiDroid data (clean first-run)..."
  adb shell pm clear com.ichi2.anki.debug >/dev/null 2>&1 || true
fi

adb install -r -t "$APK"

echo "Pushing decks to /sdcard/Download ..."
adb shell mkdir -p /sdcard/Download >/dev/null 2>&1 || true
pushed=0
for f in "$REPO"/speedrun/decks/*.apkg; do
  [ -f "$f" ] || continue
  if adb push "$f" "/sdcard/Download/$(basename "$f")" >/dev/null 2>&1; then
    echo "  + $(basename "$f")"
    pushed=$((pushed + 1))
  fi
done
echo "Pushed $pushed deck file(s)."

echo "Launching AnkiDroid..."
adb shell monkey -p com.ichi2.anki.debug -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true

cat <<'EOF'

Ready. In the emulator:
  1. Open AnkiDroid, tap "Get started" (you can skip AnkiWeb sync).
  2. The three Mixed sets (AMC 8/10/12 + GRE, interleaved) import automatically
     on first launch. To add the dedicated AMC-only or GRE-only sets: overflow
     menu (three dots) -> "Import Speedrun decks".
  3. Open e.g. "Speedrun::Mixed -> AMC 10 + GRE" -> Study. The multiple-choice
     cards are interactive: tap a choice to reveal the worked solution.
  4. Scores: overflow menu -> "Speedrun scores" (Memory / Performance /
     Readiness; abstains until you have enough data).

The app runs our shared Rust engine, so topic interleaving and topic-aware
scheduling are active on mobile (on by default in the deck config).
EOF
