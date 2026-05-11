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
      # Jinja templates aren't valid HTML; djlint owns those.
      settings.formatter.prettier.excludes = ["*.j2.html" "*.md"];
      programs.black.enable = true;
      programs.isort = {
        enable = true;
        profile = "black";
      };
      settings.formatter.black.options = ["--target-version=py310"];
    };
    treefmtFor = pkgs: (treefmt-nix.lib.evalModule pkgs treefmtConfig).config.build.wrapper;

    # htmx vendored as a fixed-output derivation. The e2e tests run in a
    # network-less Nix sandbox; without a local copy htmx never loads and
    # nothing swaps. Pin to the exact version + integrity the template
    # references so we're testing the same code prod runs.
    htmxJs = pkgs:
      pkgs.fetchurl {
        name = "htmx-1.9.5.min.js";
        url = "https://unpkg.com/htmx.org@1.9.5";
        sha256 = "0hnhsmhl59w7g8ivi76xw519p7abwzqjgcx3ps48zgz33izqiabn";
      };
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
        # Pin Playwright's browser binaries to the Nix store so neither
        # the devshell nor `nix flake check` ever fetches them at runtime.
        PLAYWRIGHT_BROWSERS_PATH = pkgs.playwright-driver.browsers;
        PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = "1";
        # See `htmxJs` above — e2e tests use this to stub the CDN.
        TRAVELLER_HTMX_JS = htmxJs pkgs;
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

    # `nix flake check` runs all of these. They each get a fresh, writable
    # copy of the source tree so the tools can scribble caches into it.
    checks = forAllSystems (pkgs: let
      python = pkgs.python3;
      testEnv = python.withPackages (project.renderers.withPackages {
        inherit python;
        extras = ["test"];
      });
      runOnSrc = name: nativeBuildInputs: env: script:
        pkgs.runCommand name ({inherit nativeBuildInputs;} // env) ''
          cp -r --no-preserve=mode ${./.} ./src
          cd ./src
          export HOME=$TMPDIR
          ${script}
          touch $out
        '';
    in {
      # pytest sees the e2e tests, so it needs Playwright's browsers
      # available offline and the sandbox-friendly env vars set.
      #
      # The Chromium quirks below are load-bearing: Playwright 1.49+
      # uses chromium-headless-shell by default, which on NixOS ships
      # without fontconfig wiring and SIGTRAPs during font rendering
      # the moment a page paints (nixpkgs #481895). We point
      # FONTCONFIG_{PATH,FILE} at the real fontconfig so the shell can
      # render text without crashing.
      pytest = runOnSrc "pytest-check" [testEnv pkgs.fontconfig] {
        PLAYWRIGHT_BROWSERS_PATH = "${pkgs.playwright-driver.browsers}";
        PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = "1";
        PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS = "true";
        FONTCONFIG_PATH = "${pkgs.fontconfig.out}/etc/fonts";
        FONTCONFIG_FILE = "${pkgs.fontconfig.out}/etc/fonts/fonts.conf";
        TRAVELLER_HTMX_JS = "${htmxJs pkgs}";
      } "pytest -p no:cacheprovider --browser chromium --browser firefox";
      treefmt = runOnSrc "treefmt-check" [(treefmtFor pkgs)] {} "treefmt --ci --no-cache";
      djlint = runOnSrc "djlint-check" [pkgs.djlint] {} "djlint --check --lint traveller/templates";
    });

    nixosModules.default = {
      config,
      lib,
      pkgs,
      ...
    }: let
      cfg = config.services.traveller;
    in {
      options.services.traveller = {
        enable = lib.mkEnableOption "the Traveller travel planning web app";

        package = lib.mkOption {
          type = lib.types.package;
          default = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
          defaultText = lib.literalExpression "traveller.packages.\${system}.default";
          description = "The traveller package to use.";
        };

        bind = lib.mkOption {
          type = lib.types.str;
          default = "127.0.0.1:8000";
          example = "unix:/run/traveller/traveller.sock";
          description = "Address gunicorn binds to (passed verbatim as --bind).";
        };

        workers = lib.mkOption {
          type = lib.types.ints.positive;
          default = 2;
          description = "Number of gunicorn worker processes.";
        };

        extraArgs = lib.mkOption {
          type = lib.types.listOf lib.types.str;
          default = [];
          example = ["--access-logfile" "-" "--timeout" "60"];
          description = "Extra arguments forwarded to gunicorn.";
        };
      };

      config = lib.mkIf cfg.enable {
        systemd.services.traveller = {
          description = "Traveller travel planning web app";
          wantedBy = ["multi-user.target"];
          after = ["network.target"];

          serviceConfig = {
            ExecStart = lib.escapeShellArgs ([
                "${cfg.package}/bin/traveller"
                "--bind"
                cfg.bind
                "--workers"
                (toString cfg.workers)
              ]
              ++ cfg.extraArgs);

            DynamicUser = true;
            StateDirectory = "traveller";
            WorkingDirectory = "%S/traveller";
            Restart = "on-failure";

            # Hardening
            ProtectSystem = "strict";
            ProtectHome = true;
            NoNewPrivileges = true;
            PrivateTmp = true;
            PrivateDevices = true;
            ProtectKernelTunables = true;
            ProtectKernelModules = true;
            ProtectControlGroups = true;
            RestrictAddressFamilies = ["AF_UNIX" "AF_INET" "AF_INET6"];
            LockPersonality = true;
            RestrictRealtime = true;
            SystemCallArchitectures = "native";
          };
        };
      };
    };
  };
}
