#!/usr/bin/env python3
"""Compiles package C# against Unity's and the project's assemblies without the editor.

    scripts/compile-check.py Packages/net.wirenook.cass
    scripts/compile-check.py modules/locomotion/Packages/net.wirenook.locomotion

Type-checks everything under the given package directories (Runtime, Editor
and Tests alike) as one assembly, referencing the installed Unity editor and
whatever the project last compiled into Library/ScriptAssemblies. It catches
the errors the editor would, in seconds, and leaves the running editor alone,
so several people (or agents) can iterate at once and only refresh Unity with
code that already builds.

It is a type check, not the real build: assembly-definition boundaries are
not enforced, and it needs the project to have been opened in Unity once so
Library/ScriptAssemblies exists.
"""

import functools
import json
import pathlib
import re
import struct
import subprocess
import sys

ROOT = pathlib.Path(
    subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
        cwd=pathlib.Path(__file__).resolve().parent,
    ).stdout.strip()
)


def unity_managed() -> pathlib.Path:
    version = re.search(
        r"m_EditorVersion: (\S+)", (ROOT / "ProjectSettings" / "ProjectVersion.txt").read_text()
    ).group(1)
    for hub in (pathlib.Path("C:/Program Files/Unity/Hub/Editor"), pathlib.Path("/Applications/Unity/Hub/Editor")):
        managed = hub / version / "Editor" / "Data" / "Managed"
        if managed.is_dir():
            return managed
    raise SystemExit(f"compile-check: Unity {version} is not installed under Unity Hub")


def is_managed(dll: pathlib.Path) -> bool:
    """True when the PE file carries a CLR header; native plugins do not."""
    try:
        data = dll.read_bytes()
        pe = struct.unpack_from("<I", data, 0x3C)[0]
        magic = struct.unpack_from("<H", data, pe + 24)[0]
        directories = pe + 24 + (96 if magic == 0x10B else 112)
        return struct.unpack_from("<I", data, directories + 14 * 8)[0] != 0
    except (struct.error, OSError):
        return False


DEFINES = ["UNITY_EDITOR", "UNITY_2022_3_OR_NEWER", "UNITY_2022_1_OR_NEWER", "UNITY_INCLUDE_TESTS", "VRC_SDK_VRCSDK3"]


@functools.lru_cache(maxsize=None)
def installed() -> frozenset:
    """The packages this project has, by name."""
    lock = ROOT / "Packages" / "packages-lock.json"
    names = {path.name for path in (ROOT / "Packages").iterdir() if path.is_dir()}
    if lock.exists():
        names |= set(json.loads(lock.read_text(encoding="utf-8")).get("dependencies", {}))
    return frozenset(names)


def left_out(source: pathlib.Path, package: pathlib.Path) -> bool:
    """True for a source Unity would not compile here: its assembly definition asks for a
    define that this project does not make. A package that serves worlds and avatars
    alike keeps each side in an assembly that only exists where its SDK is installed."""
    folder = source.parent
    while True:
        for asmdef in folder.glob("*.asmdef"):
            data = json.loads(asmdef.read_text(encoding="utf-8"))
            made = set(DEFINES) | {
                entry["define"] for entry in data.get("versionDefines", []) if entry.get("name") in installed()
            }
            return any(
                (constraint[1:] in made) if constraint.startswith("!") else (constraint not in made)
                for constraint in data.get("defineConstraints", [])
            )
        if folder == package or folder.parent == folder:
            return False
        folder = folder.parent


def main() -> int:
    packages = [pathlib.Path(argument).resolve() for argument in sys.argv[1:]]
    if not packages:
        raise SystemExit(__doc__)

    sources = [
        source for package in packages for source in package.rglob("*.cs")
        if not left_out(source, package)
    ]
    if not sources:
        print("compile-check: no C# under the given directories; nothing to do")
        return 0

    # Assemblies the checked packages themselves produce would collide with
    # their own sources, so leave those out of the references.
    own = {
        re.search(r'"name"\s*:\s*"([^"]+)"', asmdef.read_text(encoding="utf-8")).group(1)
        for package in packages
        for asmdef in package.rglob("*.asmdef")
    }

    managed = unity_managed()
    references = {}
    candidates = [
        *(managed / "UnityEngine").glob("*.dll"),
        *(ROOT / "Library" / "ScriptAssemblies").glob("*.dll"),
        *(ROOT / "Packages").glob("*/**/*.dll"),
        *(ROOT / "Library" / "PackageCache").glob("*/**/*.dll"),
        *(managed.parent / "NetStandard" / "ref" / "2.1.0").glob("netstandard.dll"),
        # Assemblies built against the .NET Framework profile (NDMF, the SDK)
        # name mscorlib; Unity resolves that through these forwarding shims.
        *(managed.parent / "NetStandard" / "compat" / "2.1.0" / "shims" / "netfx").glob("*.dll"),
        *(managed / "UnityEngine").parent.glob("UnityEditor*.dll"),
    ]
    for dll in candidates:
        if dll.stem in own or dll.stem in references or not is_managed(dll):
            continue
        # Plugins switched off for the editor (player-only builds of an
        # assembly that also ships an editor build) would define types twice.
        meta = dll.with_name(dll.name + ".meta")
        if meta.exists() and "Exclude Editor: 1" in meta.read_text(encoding="utf-8", errors="replace"):
            continue
        references[dll.stem] = dll
    nunit = next((ROOT / "Library" / "PackageCache").glob("com.unity.ext.nunit*/net35/unity-custom/nunit.framework.dll"), None)
    if nunit:
        references.setdefault("nunit.framework", nunit)

    out = ROOT / "dist" / "compile-check"
    out.mkdir(parents=True, exist_ok=True)
    project = out / "CompileCheck.csproj"
    lines = [
        '<Project Sdk="Microsoft.NET.Sdk">',
        "  <PropertyGroup>",
        "    <TargetFramework>netstandard2.1</TargetFramework>",
        "    <LangVersion>9.0</LangVersion>",
        "    <EnableDefaultCompileItems>false</EnableDefaultCompileItems>",
        "    <DisableImplicitFrameworkReferences>true</DisableImplicitFrameworkReferences>",
        "    <NoStdLib>true</NoStdLib>",
        "    <GenerateAssemblyInfo>false</GenerateAssemblyInfo>",
        "    <Nullable>disable</Nullable>",
        "    <NoWarn>$(NoWarn);CS0649;CS0169;CS0414;CS1701;CS1702;MSB3277;MSB3243</NoWarn>",
        "    <DefineConstants>" + ";".join(DEFINES) + "</DefineConstants>",
        "  </PropertyGroup>",
        "  <ItemGroup>",
        *(f'    <Compile Include="{source}" />' for source in sources),
        "  </ItemGroup>",
        "  <ItemGroup>",
        *(
            f'    <Reference Include="{name}"><HintPath>{path}</HintPath><Private>false</Private></Reference>'
            for name, path in sorted(references.items())
        ),
        "  </ItemGroup>",
        "</Project>",
    ]
    project.write_text("\n".join(lines) + "\n", encoding="utf-8")

    build = subprocess.run(
        ["dotnet", "build", str(project), "--nologo", "-v", "q", "-clp:NoSummary"],
        capture_output=True, text=True,
    )
    seen = set()
    for line in (build.stdout + build.stderr).splitlines():
        match = re.search(r"^(.*\.cs)\((\d+),(\d+)\): (error|warning) (\w+): (.*?) \[", line)
        if not match or line in seen:
            continue
        seen.add(line)
        path, row, column, kind, code, message = match.groups()
        if kind == "error":
            relative = pathlib.Path(path).resolve()
            try:
                relative = relative.relative_to(ROOT)
            except ValueError:
                pass
            print(f"{relative.as_posix()}:{row}:{column}: {code}: {message}")
    if build.returncode != 0:
        if not seen:
            print(build.stdout[-3000:], build.stderr[-2000:])
        print("compile-check: FAILED")
        return 1
    print(f"compile-check: ok ({len(sources)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
