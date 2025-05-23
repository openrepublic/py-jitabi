# meant to be used with this nixpkgs fork+branch:
#     - https://github.com/guilledk/nixpkgs/tree/cpython-debug
#
# already merged upstream:
#     - https://github.com/NixOS/nixpkgs/pull/409943
#
# -$ nix-shell --argstr pythonVersion "312" debug.nix
{
  pkgs ? import <nixpkgs> {},
  pythonVersion ? "310"
}:

let
  python = builtins.getAttr ("python${pythonVersion}") pkgs;
  pythonDebug = python.override { enableDebug = true; };
  baseShell = import ./default.nix { inherit pkgs; };
in

baseShell.overrideAttrs (old: {
  nativeBuildInputs = old.nativeBuildInputs ++ [ pythonDebug ];
  UV_PYTHON = "${pythonDebug}/bin/python3";
})

