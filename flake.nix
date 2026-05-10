{
  description = "Traveller — a travel planning Flask web app";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    treefmt-nix = {
      url = "github:numtide/treefmt-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = {
    self,
    nixpkgs,
    pyproject-nix,
    treefmt-nix,
  }: let
    inherit (nixpkgs) lib;
    systems = ["x86_64-linux" "aarch64-linux" "x86_64-darwin"];
    forAllSystems = f: lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});

    # pyproject.toml is the single source of truth for everything Python.
    # pyproject-nix translates its metadata into buildPythonPackage and
    # python.withPackages arguments.
    project = pyproject-nix.lib.project.loadPyproject {
      projectRoot = ./.;
    };

    treefmtConfig = {
      projectRootFile = "flake.nix";
      programs.alejandra.enable = true;
      programs.prettier.enable = true;
      programs.black.enable = true;
      programs.isort = {
        enable = true;
        profile = "black";
      };
      settings.formatter.black.options = ["--target-version=py310"];
    };
    treefmtFor = pkgs: (treefmt-nix.lib.evalModule pkgs treefmtConfig).config.build.wrapper;
  in {
    packages = forAllSystems (pkgs: let
      python = pkgs.python3;
    in rec {
      default = traveller;
      traveller = python.pkgs.buildPythonApplication (
        project.renderers.buildPythonPackage {inherit python;}
      );
    });

    devShells = forAllSystems (pkgs: let
      python = pkgs.python3;
      addFlags = package: flags:
        pkgs.symlinkJoin {
          name = package.name;
          paths = [package];
          buildInputs = [pkgs.makeWrapper];
          postBuild = "wrapProgram $out/bin/${package.pname}" + builtins.concatStringsSep " --add-flags " ([""] ++ flags);
        };
    in {
      default = pkgs.mkShell {
        name = "traveller";
        packages = [
          pkgs.git
          pkgs.coreutils
          pkgs.moreutils
          pkgs.diffutils
          pkgs.pre-commit

          (python.withPackages (project.renderers.withPackages {
            inherit python;
            extras = ["dev"];
          }))

          pkgs.stylelint
          pkgs.djhtml
          pkgs.djlint

          pkgs.ruff
          pkgs.black
          (addFlags pkgs.mypy ["--ignore-missing-imports"])
          (addFlags pkgs.isort ["--profile=black"])

          (treefmtFor pkgs)

          (pkgs.writeShellScriptBin "run_server" ''
            gunicorn -b 0.0.0.0:8000 --reload \
            $(find templates -type f -name '*.j2.html' -exec echo --reload-extra-file {} \;) \
            traveller.app:create_app\(\) \
            sleep 1
          '')
        ];
      };
    });

    formatter = forAllSystems treefmtFor;
  };
}
