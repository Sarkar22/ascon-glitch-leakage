#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build the pull-request folder and run the organizers' CI on it, in a clone of their repository.
#   bash tools/check_submission.sh [OUTDIR]          (default OUTDIR: runs/submission, git-ignored)
# 1. tools/make_submission.py, in the cac-sca image (it traces a cached run of the notebook):
#    OUTDIR/ISSCC27/submitted_notebooks/ascon_glitch_leakage/
# 2. a shallow, sparse clone of github.com/sscs-ose/sscs-ose-code-a-chip.github.io (main; only
#    ISSCC27/ and .github/ checked out) in OUTDIR/upstream, with the folder copied in
# 3. in a clean python:3.10-slim container that sees only that clone, the commands of their two
#    workflows (.github/workflows/lint.yaml, run.yaml), step by step with the shell each step gets
#    on GitHub (bash -e, or bash -eo pipefail where the step sets shell: bash):
#      exact     as written: **/*.ipynb without globstar, which matches one directory level only
#      globstar  the same commands with globstar on, so they reach ISSCC27/submitted_notebooks/*/
#    The globstar pytest --nbmake run is the notebook executed at its PR location (cached mode).
# 4. hygiene: running the notebook in step 3 wrote __pycache__/*.pyc into the clone's copy of the
#    folder, which upstream's .gitignore does not ignore; they are deleted, and the clone's copy must
#    then equal the build file for file. Also: nothing outside the folder changed (pytest's own
#    .pytest_cache/ aside), no bytecode in the build, file count and size, no host paths or e-mail
#    addresses in the folder.
# The fork's commit must be a fresh copy of the build, OUTDIR/ISSCC27/submitted_notebooks/
# ascon_glitch_leakage/, never of OUTDIR/upstream/, where the notebook has run.
# Env: CPUS (default 2). Output: OUTDIR/check.log. Exit status 0 when the globstar variant and the
# hygiene checks pass.
set -euo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUT=$(mkdir -p "${1:-$REPO/runs/submission}" && cd "${1:-$REPO/runs/submission}" && pwd)
CPUS=${CPUS:-2}
UPSTREAM=https://github.com/sscs-ose/sscs-ose-code-a-chip.github.io
DEST=ISSCC27/submitted_notebooks/ascon_glitch_leakage
exec > >(tee "$OUT/check.log") 2>&1

echo "== 1. build the folder"
case "$OUT/" in
  "$REPO"/*) DOCKER_OPTS="--cpus $CPUS" bash "$REPO/sim/docker_run.sh" \
               python3 "$REPO/tools/make_submission.py" --out-root "$OUT" ;;
  *) python3 "$REPO/tools/make_submission.py" --out-root "$OUT" ;;   # needs numpy + matplotlib
esac

echo "== 2. clone $UPSTREAM (shallow, sparse) and add the folder"
rm -rf "$OUT/upstream"
git clone -q --depth 1 --filter=blob:none --sparse "$UPSTREAM" "$OUT/upstream"
git -C "$OUT/upstream" sparse-checkout set ISSCC27 .github
git -C "$OUT/upstream" log -1 --format='upstream main: %h %cd'
mkdir -p "$OUT/upstream/$DEST"
cp -a "$OUT/$DEST/." "$OUT/upstream/$DEST/"

echo "== 3. the organizers' workflows in python:3.10-slim (--cpus $CPUS)"
set +e
docker run --rm --cpus "$CPUS" --memory 3g -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
  -v "$OUT/upstream:/w" -w /w python:3.10-slim bash -c '
trap "chown -R $HOST_UID:$HOST_GID /w" EXIT
T0=$(date +%s)
step() {   # variant, flags, name, command: one workflow step, as GitHub runs it ($pre first)
  local out rc
  out=$(bash $2 -c "$pre"$'"'"'\n'"'"'"$4" 2>&1); rc=$?
  printf "%-8s %-4s %-26s %s\n" "$1" "$rc" "$3" "$(echo "$out" | tail -n 1 | cut -c1-110)"
  [ "$1" = "globstar" ] && [ "$rc" != 0 ] && FAIL=1
  return 0
}
export DEBIAN_FRONTEND=noninteractive
apt-get -qq update >/dev/null && apt-get -yq install graphviz >/dev/null
pip install -q --root-user-action=ignore flake8 nbQA pytest nbmake pandas graphviz matplotlib 2>&1 | grep -v -i "notice" || true
python --version; pip list 2>/dev/null | grep -i -E "^(flake8|nbqa|pytest|nbmake|pandas|numpy|matplotlib) " | tr -s " " | tr "\n" " "; echo
echo "installed in $(( $(date +%s) - T0 )) s"
FAIL=0
echo "variant  exit step                       last line of output"
for v in exact globstar; do
  pre=":"; [ "$v" = globstar ] && pre="shopt -s globstar"
  step "$v" "-e" "lint: flake8" "nbqa flake8 --ignore=E402,E226 **/*.ipynb"
  step "$v" "-e" "lint: has colab-badge" "grep colab-badge **/*.ipynb"
  step "$v" "--noprofile --norc -eo pipefail" "lint: colab-badge sscs-ose" \
       "grep colab-badge **/*.ipynb | (! grep -v sscs-ose)"
  t=$(date +%s)
  step "$v" "-e" "run: pytest --nbmake" "pytest --nbmake **/*.ipynb"
  echo "         ($(( $(date +%s) - t )) s)"
done
exit $FAIL'
RC=$?
set -e

echo "== 4. hygiene"
BC=$(find "$OUT/upstream/$DEST" \( -name __pycache__ -o -name '*.pyc' -o -name '*.pyo' \) | wc -l)
find "$OUT/upstream/$DEST" -depth \( -name __pycache__ -o -name '*.pyc' -o -name '*.pyo' \) -exec rm -rf {} +
echo "bytecode written by the notebook run in the clone's copy: $BC entries, deleted"
if [ -n "$(find "$OUT/$DEST" \( -name __pycache__ -o -name '*.pyc' -o -name '*.pyo' \))" ]; then
  echo "FAIL: the build holds Python bytecode"; RC=1
else echo "no bytecode in the build"; fi
if diff -r -q "$OUT/$DEST" "$OUT/upstream/$DEST"; then
  echo "the clone's copy equals the build ($(find "$OUT/upstream/$DEST" -type f | wc -l) files)"
else echo "FAIL: the clone's copy differs from the build (above)"; RC=1; fi
git -C "$OUT/upstream" status --porcelain --untracked-files=all | grep -v -E "^\?\? ($DEST/|\.pytest_cache/)" \
  && { echo "FAIL: files outside $DEST changed"; RC=1; } || echo "only $DEST/ added"
find "$OUT/$DEST" -type f | wc -l | xargs echo "files:"
du -sh "$OUT/$DEST" | cut -f1 | xargs echo "size:"
if grep -r -n -o -I -E "(^|[^[:alnum:]._-])/(home|media|Users)/[^\" ]*|[[:alnum:]._%+-]+@[[:alnum:].-]+\.(edu|com|ca|org)" \
    "$OUT/$DEST"; then echo "FAIL: host paths or e-mail addresses above"; RC=1
else echo "no host paths or e-mail addresses"; fi
echo "== exit $RC"
exit $RC
