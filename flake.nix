{
  description = "Flask web development environment";
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
    treefmt-nix.url = "github:numtide/treefmt-nix";
  };

  outputs = inputs @ {
    self,
    flake-parts,
    ...
  }:
    flake-parts.lib.mkFlake {inherit inputs;} {
      systems = ["x86_64-linux" "aarch64-linux" "x86_64-darwin"];

      imports = [inputs.treefmt-nix.flakeModule];

      perSystem = {
        pkgs,
        config,
        ...
      }: let
        addFlags = package: flags:
          pkgs.symlinkJoin {
            name = package.name;
            paths = [package];
            buildInputs = [pkgs.makeWrapper];
            postBuild = "wrapProgram $out/bin/${package.pname}" + builtins.concatStringsSep " --add-flags " ([""] ++ flags);
          };
        ruffTOML = (pkgs.formats.toml {}).generate "ruff.toml" {
          select = ["E" "F" "D" "W" "C" "N" "ANN" "B" "A" "C4" "RSE" "RET" "SIM" "ARG" "PTH" "PD" "NPY" "PERF" "RUF"];
          ignore = ["ANN101" "D100" "RUF012"];
          pydocstyle.convention = "pep257";
        };
      in {
        devShells.default = pkgs.mkShell {
          name = "cards";
          packages = [
            pkgs.git
            pkgs.coreutils
            pkgs.moreutils
            pkgs.diffutils
            pkgs.pre-commit
            (pkgs.python3.withPackages (p: with p; [flask gunicorn python-lsp-server jupyterlab gpxpy]))

            pkgs.nodePackages.stylelint
            pkgs.djhtml
            pkgs.djlint
            pkgs.csslint

            (addFlags pkgs.ruff ["--config=${ruffTOML}"])
            (addFlags pkgs.mypy ["--ignore-missing-imports"])
            # (addFlags pkgs.black ["--target-version=py310"])
            (addFlags pkgs.isort ["--profile=black"])

            (pkgs.writeShellScriptBin "run_server" ''
              gunicorn -b 0.0.0.0:8000 --reload \
              $(find templates -type f -name '*.html.j2' -exec echo --reload-extra-file {} \;)                serve:app
              sleep 1
            '')
          ];
        };
        treefmt = {
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
      };
    };
}
