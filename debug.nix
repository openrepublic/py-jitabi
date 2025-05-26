# for now `enableDebug` param for python package requires nix-unstable channel
# usage:
#     nix-shell --argstr pythonVersion "312" debug.nix
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

