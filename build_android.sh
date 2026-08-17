#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

ANDROID_DIR="$PWD/android"
SDK_DIR="${NOVA_ANDROID_SDK:-$PWD/android-sdk}"
PLATFORM="$SDK_DIR/platforms/android-33/android.jar"
BUILD="$ANDROID_DIR/build/auto"
CLASSES="$BUILD/classes"
DEX="$BUILD/dex"
KEYSTORE="${NOVA_KEYSTORE:-$ANDROID_DIR/build/signing/nova-new.keystore}"
ALIAS="${NOVA_KEY_ALIAS:-nova}"
OUT="$BUILD/nova.apk"

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "Missing required command: $1" >&2
        exit 1
    }
}

for cmd in java javac d8 aapt zipalign apksigner keytool unzip zip; do
    need_cmd "$cmd"
done

[[ -f "$PLATFORM" ]] || {
    echo "Missing Android 33 platform: $PLATFORM" >&2
    exit 1
}
[[ -f "$ANDROID_DIR/AndroidManifest.xml" ]] || exit 1
[[ -d "$ANDROID_DIR/res" ]] || exit 1
[[ -d "$ANDROID_DIR/src" ]] || exit 1

mkdir -p "$BUILD" "$CLASSES" "$DEX" "$(dirname "$KEYSTORE")"
rm -rf "$CLASSES" "$DEX"
mkdir -p "$CLASSES" "$DEX"

echo "[1/5] Compiling Android resources..."
rm -f "$BUILD/resources.zip" "$BUILD/nova-unsigned.apk"
aapt package \
    -f \
    -M "$ANDROID_DIR/AndroidManifest.xml" \
    -S "$ANDROID_DIR/res" \
    -I "$PLATFORM" \
    -F "$BUILD/resources.zip"

echo "[2/5] Compiling Java sources..."
mapfile -t JAVA_SOURCES < <(find "$ANDROID_DIR/src" -type f -name '*.java' | sort)
[[ ${#JAVA_SOURCES[@]} -gt 0 ]] || { echo "No Java sources found." >&2; exit 1; }
javac -source 8 -target 8 -encoding UTF-8 -classpath "$PLATFORM" -d "$CLASSES" "${JAVA_SOURCES[@]}"

echo "[3/5] Building classes.dex..."
mapfile -t CLASS_FILES < <(find "$CLASSES" -type f -name '*.class' | sort)
[[ ${#CLASS_FILES[@]} -gt 0 ]] || { echo "No Java class files were produced." >&2; exit 1; }
d8 --min-api 23 --lib "$PLATFORM" --output "$DEX" "${CLASS_FILES[@]}"
[[ -f "$DEX/classes.dex" ]] || { echo "D8 did not produce classes.dex." >&2; exit 1; }

echo "[4/5] Packaging and aligning APK..."
cp "$BUILD/resources.zip" "$BUILD/nova-with-dex-unsigned.apk"
zip -q -j "$BUILD/nova-with-dex-unsigned.apk" "$DEX/classes.dex"
zipalign -f -p 4 "$BUILD/nova-with-dex-unsigned.apk" "$BUILD/nova-aligned.apk"

echo "[5/5] Signing APK..."
if [[ ! -f "$KEYSTORE" ]]; then
    echo "No Nova keystore found. Creating: $KEYSTORE"
    if [[ -z "${NOVA_KEYSTORE_PASSWORD:-}" ]]; then
        read -r -s -p "Create keystore password: " NOVA_KEYSTORE_PASSWORD
        echo
        read -r -s -p "Confirm keystore password: " confirm
        echo
        [[ "$NOVA_KEYSTORE_PASSWORD" == "$confirm" ]] || { echo "Passwords do not match." >&2; exit 1; }
    fi
    keytool -genkeypair \
        -keystore "$KEYSTORE" \
        -storepass "$NOVA_KEYSTORE_PASSWORD" \
        -keypass "$NOVA_KEYSTORE_PASSWORD" \
        -alias "$ALIAS" \
        -keyalg RSA \
        -keysize 2048 \
        -validity 10000 \
        -dname 'CN=Nova, OU=Infoney, O=Infoney, L=Sulaymaniyah, ST=Kurdistan, C=IQ'
else
    echo "Reusing existing Nova keystore: $KEYSTORE"
    if [[ -z "${NOVA_KEYSTORE_PASSWORD:-}" ]]; then
        read -r -s -p "Keystore password: " NOVA_KEYSTORE_PASSWORD
        echo
    fi
fi

rm -f "$OUT" "$OUT.idsig"
apksigner sign \
    --ks "$KEYSTORE" \
    --ks-key-alias "$ALIAS" \
    --ks-pass "pass:$NOVA_KEYSTORE_PASSWORD" \
    --key-pass "pass:$NOVA_KEYSTORE_PASSWORD" \
    --min-sdk-version 23 \
    --out "$OUT" \
    "$BUILD/nova-aligned.apk"

apksigner verify --verbose --print-certs "$OUT"

echo
echo "Nova APK built successfully:"
echo "  $OUT"
ls -lh "$OUT"
