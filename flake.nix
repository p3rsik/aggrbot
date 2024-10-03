{
  inputs = {
    nixpkgs = {
      url = "github:nixos/nixpkgs/nixos-unstable";
    };
    flake-utils = {
      url = "github:numtide/flake-utils";
    };
  };
  outputs = { nixpkgs, flake-utils, ... }: flake-utils.lib.eachDefaultSystem (system:
    let
      pkgs = import nixpkgs {
        inherit system;
      };
      python-version =
        pkgs.python3.withPackages
          (p: (with p; [
            python-lsp-server
            python-lsp-ruff
            pip
          ]));
    in
    {
      devShells.default = pkgs.mkShell {
        buildInputs = [
          python-version
        ];
        shellHook = ''
          export PIP_PREFIX=$(pwd)/_build/pip_packages # Dir where built packages are stored
          export PYTHONPATH="$PIP_PREFIX/${pkgs.python3.sitePackages}:$PYTHONPATH"
          export PATH="$PIP_PREFIX/bin:$PATH"
          unset SOURCE_DATE_EPOCH
        '';
      };
    }
  );
}
