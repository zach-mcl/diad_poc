#!/bin/bash

set -e

echo "Building .PKG Installer"

project_directory="$(cd "$(dirname "$0")" && pwd)"
build_directory="$project_directory/pkg_build"
payload_directory="$build_directory/payload/Applications/.diad"
scripts_directory="$build_directory/scripts"
app_bundle="$payload_directory/DIAD.app"
output_package="$project_directory/dist/DIAD-Installer.pkg"



rm -rf "$build_directory"
mkdir -p "$payload_directory" "$scripts_directory" "$(dirname "$output_package")"

echo "Copying app files"
mkdir -p "$payload_directory/app"
mkdir -p "$payload_directory/UI"
#making directories for copy
cp "$project_directory/app/__init__.py" "$payload_directory/app/"
cp "$project_directory/app/console_ui.py" "$payload_directory/app/"
cp "$project_directory/app/db.py" "$payload_directory/app/"
cp "$project_directory/app/llm.py" "$payload_directory/app/"
cp "$project_directory/app/main.py" "$payload_directory/app/"
cp "$project_directory/app/query_plan.py" "$payload_directory/app/"
cp "$project_directory/app/router.py" "$payload_directory/app/"
cp "$project_directory/app/sql_flow.py" "$payload_directory/app/"
cp "$project_directory/app/validate.py" "$payload_directory/app/"
cp "$project_directory/app/router_types.py" "$payload_directory/app/"
cp "$project_directory/app/schema_aliases.py" "$payload_directory/app/"
cp "$project_directory/app/data_questions.py" "$payload_directory/app/"
cp "$project_directory/app/projects.py" "$payload_directory/app/"
cp "$project_directory/app/python_tools.py" "$payload_directory/app/"
#/app copies ^
cp "$project_directory/UI/__init__.py" "$payload_directory/UI/"
cp "$project_directory/UI/app.py" "$payload_directory/UI/"
cp "$project_directory/UI/controller.py" "$payload_directory/UI/"
cp "$project_directory/UI/state.py" "$payload_directory/UI/"
#/UI copies ^
cp "$project_directory/run_ui.py" "$payload_directory/"
cp "$project_directory/requirements.txt" "$payload_directory/"
cp -r "$project_directory/tkdnd_tcl9" "$payload_directory/"
#root copies ^
cp "$project_directory/diadlauncher" "$payload_directory/"
cp "$project_directory/Info.plist" "$payload_directory/"

echo "Creating launcher bundle"
mkdir -p "$app_bundle/Contents/MacOS"
mkdir -p "$app_bundle/Contents/Resources"

cp "$project_directory/diadlauncher" "$app_bundle/Contents/MacOS/diadlauncher"
chmod +x "$app_bundle/Contents/MacOS/diadlauncher"
#finds launcher script and gives permissions ^

cp "$project_directory/Info.plist" "$app_bundle/Contents/"
#copies over Plist




cp "$project_directory/postinstall" "$scripts_directory/postinstall"
chmod +x "$scripts_directory/postinstall"
#finds postinstall script and gives permissions ^

echo "Building .pkg"
pkgbuild \
    --root "$build_directory/payload" \
    --scripts "$scripts_directory" \
    --identifier "com.diad.app" \
    --version "1.0.0" \
    --install-location "/" \
    "$output_package"

echo "Build Complete"
echo "Installer: $output_package"
#builds and completes package ^

