#!/bin/sh
# Llena la caché de Tectonic con los documentos de precarga (F6-K, D-227, D-230). Uso: precarga.sh <tectonic> <caché>.
# Clases (article, report, book, KOMA, memoir, letter, beamer), paquetes habituales de tesis y apuntes y los estilos de
# BibTeX más usados: cada estilo necesita una compilación con su \bibliographystyle para que Tectonic descargue su .bst.
set -eu
exe="$1"; cache="$2"; here="$(cd "$(dirname "$0")" && pwd)"
tmp="$(mktemp -d)"
cp "$here/precarga.tex" "$here/precarga-beamer.tex" "$tmp/"
cat > "$tmp/refs.bib" <<'BIB'
@article{knuth84, author = {Donald E. Knuth}, title = {Literate Programming}, journal = {The Computer Journal}, year = {1984}, volume = {27}, pages = {97--111}}
@book{lamport94, author = {Leslie Lamport}, title = {{\LaTeX}: A Document Preparation System}, publisher = {Addison-Wesley}, year = {1994}}
BIB
for cls in report book scrartcl scrreprt scrbook memoir; do
  cat > "$tmp/c-$cls.tex" <<TEX
\\documentclass{$cls}
\\usepackage[spanish]{babel}
\\usepackage{lmodern,cleveref,makeidx,multicol,wrapfig,appendix,ragged2e,algorithm,algpseudocode,pdfpages,xurl,tocbibind}
\\makeindex
\\begin{document}
\\tableofcontents
\\chapter{Uno}\\label{c}Ver \\cref{c}.
\\end{document}
TEX
done
sed -i 's/\\chapter{Uno}/\\section{Uno}/' "$tmp/c-scrartcl.tex"
printf '\\documentclass{letter}\\begin{document}\\begin{letter}{A}\\opening{Hola}x\\closing{Adiós}\\end{letter}\\end{document}\n' > "$tmp/c-letter.tex"
for st in plain alpha abbrv unsrt ieeetr apalike siam acm plainnat unsrtnat abbrvnat; do
  case "$st" in *nat) pkg='\usepackage{natbib}' ;; *) pkg='' ;; esac
  printf '\\documentclass{article}%s\\begin{document}Texto \\cite{knuth84}.\\nocite{*}\\bibliographystyle{%s}\\bibliography{refs}\\end{document}\n' "$pkg" "$st" > "$tmp/b-$st.tex"
done
cd "$tmp"
for f in precarga.tex precarga-beamer.tex c-*.tex b-*.tex; do
  TECTONIC_CACHE_DIR="$cache" "$exe" -X compile "$f" >/dev/null
done
printf '\\documentclass{article}\\usepackage[backend=bibtex]{biblatex}\\addbibresource{refs.bib}\\begin{document}Texto \\cite{knuth84}.\\printbibliography\\end{document}\n' > biblatex.tex
TECTONIC_CACHE_DIR="$cache" "$exe" -X compile biblatex.tex >/dev/null
# Comprobación: con --only-cached, el informe y la bibliografía compilan sin red y sin citas sin resolver.
TECTONIC_CACHE_DIR="$cache" "$exe" -X compile --only-cached c-report.tex >/dev/null
TECTONIC_CACHE_DIR="$cache" "$exe" -X compile --only-cached --keep-intermediates b-plain.tex >/dev/null
grep -q "Knuth" b-plain.bbl
cd /
rm -r "$tmp"
