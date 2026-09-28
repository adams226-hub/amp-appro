#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
: "${ANDROID_SDK_ROOT:?Définir ANDROID_SDK_ROOT}"
BT="${BUILD_TOOLS_DIR:-$ANDROID_SDK_ROOT/build-tools/35.0.0}"
PLATFORM="$ANDROID_SDK_ROOT/platforms/android-35/android.jar"
mkdir -p build/classes build/dex
if [[ -n "${ECJ_JAR:-}" ]]; then
 java -jar "$ECJ_JAR" -8 -nowarn -cp "$PLATFORM" -d build/classes android/src/bf/amp/appro/MainActivity.java
else
 javac -source 8 -target 8 -classpath "$PLATFORM" -d build/classes android/src/bf/amp/appro/MainActivity.java
fi
"$BT/aapt2" compile --dir android/res -o build/res.zip
"$BT/aapt2" link -o build/base.apk --manifest android/AndroidManifest.xml -I "$PLATFORM" -A android/assets build/res.zip
python3 - <<'PY'
from pathlib import Path
from zipfile import ZipFile
with ZipFile('build/classes.jar','w') as z:
 for p in Path('build/classes').rglob('*.class'):z.write(p,p.relative_to('build/classes'))
PY
"$BT/d8" --lib "$PLATFORM" --min-api 26 --output build/dex build/classes.jar
python3 - <<'PY'
from zipfile import ZipFile
with ZipFile('build/base.apk','a') as z:z.write('build/dex/classes.dex','classes.dex')
PY
"$BT/zipalign" -f 4 build/base.apk build/aligned.apk
if [[ ! -f signing/pilot.keystore ]]; then
 mkdir -p signing
 keytool -genkeypair -keystore signing/pilot.keystore -storepass android -keypass android -alias androiddebugkey -dname 'CN=AMP Appro Pilot,O=Prototype,C=BF' -keyalg RSA -keysize 2048 -validity 3650
fi
"$BT/apksigner" sign --ks signing/pilot.keystore --ks-pass pass:android --out AMP_Appro_Pilote.apk build/aligned.apk
"$BT/apksigner" verify --verbose AMP_Appro_Pilote.apk
