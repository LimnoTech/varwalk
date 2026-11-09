"""varwalk: variable crosswalks for water and environmental data.

This ``__init__`` imports nothing, so ``import varwalk`` stays light:
pint, pandas and xarray load only when a submodule that needs them is
imported. Import submodules by path, for example
``from varwalk import registry``.

- ``registry``: the private pint registry, the year setting, CF
  formatting.
- ``qudt`` and ``validate``: the shipped QUDT subset, dimension
  vectors, quantity kinds.
- ``annotate``: ``annotate``, ``validate_annotations``, ``read_table``.
- ``convert``: ``convert_units``, ``rate_to_amount``.
- ``chemistry``: ``convert_basis``, ``convert_amount``.
- ``dictionary``: the data-dictionary fields and helpers.
- ``variables``: the variable model, ``variables_frame``,
  ``describe_variables``, ``check_udunits``.
- ``warnings``: the ``AnnotationWarning`` classes and ``warn``.
"""


def __getattr__(name: str) -> str:
    # Read lazily, so importing the package imports nothing at all.
    if name == "__version__":
        try:
            from varwalk._version import __version__
        except ImportError as error:  # not built: no generated file
            raise AttributeError(
                "varwalk has no __version__ until it is built"
            ) from error
        return __version__
    raise AttributeError(f"module 'varwalk' has no attribute {name!r}")
