# tex-writer-studio

A simple LaTeX editor and PDF compiler with live source-to-document navigation.


## Install from PYPI

The homepage in pipy is https://pypi.org/project/tex_writer_studio/

```bash
pip install --upgrade tex_writer_studio
```

or (recommended for desktop applications)

```bash
pipx install tex_writer_studio
```


Using:

```bash
tex-writer-studio
```

If you would like the program to initialize at the start of the Linux session, use `tex-writer-studio --autostart`.

## Install from source
Installing `tex-writer-studio` program

```bash
git clone https://github.com/trucomanx-desktop/TeXWriterStudio.git
cd TeXWriterStudio
pip install -r requirements.txt
cd src
python -m build
pip install dist/tex_writer_studio-*.tar.gz
```
Using:

```bash
tex-writer-studio
```

## Uninstall

```bash
pip uninstall tex_writer_studio
```
