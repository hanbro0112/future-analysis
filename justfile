# 只支援 linux base shell (windows 可以用 git bash)

ROOT_DIR := justfile_directory()


dev:
    cd skills
    pnpm install


    firebase emulators:start

init:
    node --version
    npm --version
    pnpm --version
    just --version
    npm install -g firebase-tools

