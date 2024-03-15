{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
  };

  outputs = {
    self,
    nixpkgs,
    flake-parts,
  } @ inputs:
    flake-parts.lib.mkFlake {inherit inputs;} {
      systems = ["x86_64-linux"];

      perSystem = {pkgs, ...}: {
        formatter = pkgs.alejandra;
        devShells.default = pkgs.mkShell {
          name = "seashell";
          packages = with pkgs; [
            bash
            git
            coreutils
            moreutils
            diffutils
            (python310.withPackages (ps: with ps; [python-telegram-bot flask apscheduler uvicorn starlette]))
            black
            isort
          ];
        };
      };
    };
}
