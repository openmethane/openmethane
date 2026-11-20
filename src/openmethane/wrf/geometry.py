"""The geometry of WRF domains, and how a set of them is numbered for a run.

WRF numbers the domains in a run 1, 2, 3 and so on, with every parent before its
nests, and names their files `d01`, `d02`. That numbering belongs to a run, not
to a domain: the same nest can be `d02` in one run and `d03` in another.
`DomainSet` assigns it.

Until the domain file carries WRF's geometry (#297), each domain's geometry is
read from a small YAML file, `openmethane/wrf/domains/<name>/<version>.yaml`,
using the attribute names #297 proposes, so the switch to the domain file
mostly changes the reader.
"""

import importlib.resources
import math
from collections.abc import Iterable, Sequence

import attrs
import attrs.validators
import yaml

MAP_PROJECTIONS = ("lambert", "polar", "mercator", "lat-lon")
"""Values WPS accepts for `map_proj`"""


class GeometryError(ValueError):
    """A domain's geometry, or a set of domains, can't be run."""


def _positive(instance, attribute, value):
    if value <= 0:
        raise ValueError(f"{attribute.name} must be positive, got {value}")


@attrs.frozen
class DomainGeometry:
    """The WRF geometry of one domain, in WPS's terms."""

    name: str
    """The domain's name, such as aust10km"""
    version: str
    """The domain's published version, such as v1. A nest's version needn't match its parent's"""
    map_proj: str = attrs.field(validator=attrs.validators.in_(MAP_PROJECTIONS))
    """WPS map projection"""
    ref_lat: float
    """Latitude of the reference point, degrees"""
    ref_lon: float
    """Longitude of the reference point, degrees"""
    truelat1: float
    """First true latitude of the projection, degrees"""
    truelat2: float
    """Second true latitude of the projection, degrees"""
    stand_lon: float
    """Standard longitude of the projection, degrees"""
    e_we: int = attrs.field(validator=_positive)
    """Staggered grid size west to east, as in the namelist: one more than the number of cells"""
    e_sn: int = attrs.field(validator=_positive)
    """Staggered grid size south to north"""
    dx: float = attrs.field(validator=_positive)
    """Grid spacing west to east, metres. For a nest, its parent's dx over the ratio"""
    dy: float = attrs.field(validator=_positive)
    """Grid spacing south to north, metres"""
    geog_data_res: str
    """Static geography datasets geogrid used, such as 'usgs_30s+default'"""
    ref_x: float | None = None
    """Grid position of the reference point. None centres the domain on it"""
    ref_y: float | None = None
    """Grid position of the reference point. None centres the domain on it"""
    parent: str | None = None
    """Name of the domain this one is nested in, or None for an outer domain"""
    parent_grid_ratio: int = attrs.field(default=1, validator=_positive)
    """Parent cells per nest cell along each side. 1 for an outer domain"""
    i_parent_start: int = attrs.field(default=1, validator=_positive)
    """Parent column, 1-based, of the nest's lower-left corner. 1 for an outer domain"""
    j_parent_start: int = attrs.field(default=1, validator=_positive)
    """Parent row, 1-based, of the nest's lower-left corner. 1 for an outer domain"""

    @property
    def is_nest(self) -> bool:
        """Whether the domain is nested in another."""
        return self.parent is not None

    @classmethod
    def from_attributes(cls, name: str, version: str, attributes: dict) -> "DomainGeometry":
        """
        Build a geometry from #297's domain attributes.

        Parameters
        ----------
        name
            The domain's name.
        version
            The domain's published version.
        attributes
            The domain's attributes. `wrf_` attributes and `parent_domain_name`
            are read, and other attributes, which describe the domain for
            other programs, are ignored. An unknown `wrf_` attribute is an
            error, so a typo isn't silently ignored.
        """
        fields = {}
        unknown = []
        for key, value in attributes.items():
            if key == "parent_domain_name":
                fields["parent"] = value
            elif key.startswith("wrf_"):
                if key[4:] in _ATTRIBUTE_FIELDS:
                    fields[key[4:]] = value
                else:
                    unknown.append(key)
        if unknown:
            raise GeometryError(f"Unknown attributes for domain {name}: {', '.join(unknown)}")
        try:
            return cls(name=name, version=version, **fields)
        except TypeError as error:
            raise GeometryError(f"Incomplete geometry for domain {name}: {error}") from error


_ATTRIBUTE_FIELDS = {field.name for field in attrs.fields(DomainGeometry)} - {
    "name",
    "version",
    "parent",
}


def load_geometry(name: str, version: str) -> DomainGeometry:
    """
    Load a domain's geometry from the files shipped with openmethane.

    Parameters
    ----------
    name
        The domain's name, such as aust10km.
    version
        The published version of the domain, such as v1.

    Raises
    ------
    GeometryError
        If there is no geometry for that version of the domain, or it is invalid.
    """
    domains = importlib.resources.files("openmethane.wrf.domains")
    resource = domains / name / f"{version}.yaml"
    if not resource.is_file():
        known = sorted(
            f"{entry.name} {version_file.name.removesuffix('.yaml')}"
            for entry in domains.iterdir()
            if entry.is_dir() and not entry.name.startswith("_")
            for version_file in entry.iterdir()
            if version_file.name.endswith(".yaml")
        )
        raise GeometryError(
            f"No WRF geometry for domain {name!r} version {version!r}. Known: {', '.join(known)}"
        )
    return DomainGeometry.from_attributes(name, version, yaml.safe_load(resource.read_text()))


@attrs.frozen
class Domain:
    """A domain as it runs in one WRF run: its geometry and its WRF number."""

    geometry: DomainGeometry
    index: int
    """WRF's 1-based number for the domain in this run, `grid_id`"""
    parent_index: int
    """`index` of the parent, or 1 for the outer domain, as WRF's `parent_id` expects"""
    dx: float
    """Grid spacing west to east, metres"""
    dy: float
    """Grid spacing south to north, metres"""

    @property
    def id(self) -> str:
        """WRF's name for the domain in file names, such as d01."""
        return f"d{self.index:02d}"

    @property
    def name(self) -> str:
        return self.geometry.name

    @property
    def version(self) -> str:
        return self.geometry.version


@attrs.frozen
class DomainSet:
    """
    The domains that run together, numbered as WRF needs.

    Domains are sorted parent first, by nesting depth, keeping the given order
    among domains at the same depth. The order of siblings changes a nest's
    output at the level of noise (#296), so the same input always gives the
    same numbering.
    """

    domains: tuple[Domain, ...]

    @classmethod
    def from_geometries(cls, geometries: Iterable[DomainGeometry]) -> "DomainSet":
        """
        Number a set of domains for a run.

        Raises
        ------
        GeometryError
            Unless there is exactly one outer domain, every nest's parent is in
            the set, and names are unique.
        """
        geometries = list(geometries)
        by_name = {geometry.name: geometry for geometry in geometries}
        if len(by_name) != len(geometries):
            raise GeometryError(f"Domain names repeat: {[g.name for g in geometries]}")

        outer = [geometry for geometry in geometries if not geometry.is_nest]
        if len(outer) != 1:
            raise GeometryError(
                f"A run needs exactly one outer domain, got {len(outer)}:"
                f" {[g.name for g in outer]}"
            )
        for geometry in geometries:
            if geometry.is_nest and geometry.parent not in by_name:
                raise GeometryError(
                    f"Domain {geometry.name} is nested in {geometry.parent}, which isn't in the run"
                )

        def depth(geometry: DomainGeometry) -> int:
            seen = []
            while geometry.is_nest:
                if geometry.name in seen:
                    raise GeometryError(f"Domains are nested in a loop: {seen}")
                seen.append(geometry.name)
                geometry = by_name[geometry.parent]
            return len(seen)

        # sorted() is stable, so domains at one depth keep the given order.
        ordered = sorted(geometries, key=depth)
        index_of = {geometry.name: number for number, geometry in enumerate(ordered, start=1)}

        domains = []
        for geometry in ordered:
            if geometry.is_nest:
                parent = domains[index_of[geometry.parent] - 1]
                dx = parent.dx / geometry.parent_grid_ratio
                dy = parent.dy / geometry.parent_grid_ratio
                # WRF derives a nest's spacing from its parent's, so a
                # different value in the geometry is a mistake somewhere.
                if not (math.isclose(geometry.dx, dx) and math.isclose(geometry.dy, dy)):
                    raise GeometryError(
                        f"Domain {geometry.name} has spacing {geometry.dx} x {geometry.dy},"
                        f" but its parent's over the ratio is {dx} x {dy}"
                    )
                parent_index = parent.index
            else:
                dx, dy, parent_index = geometry.dx, geometry.dy, 1
            domains.append(
                Domain(
                    geometry=geometry,
                    index=index_of[geometry.name],
                    parent_index=parent_index,
                    dx=dx,
                    dy=dy,
                )
            )
        return cls(tuple(domains))

    @classmethod
    def load(cls, domains: Sequence[tuple[str, str]]) -> "DomainSet":
        """Number the domains, given as (name, version), with geometry from `load_geometry`."""
        return cls.from_geometries(load_geometry(name, version) for name, version in domains)

    @property
    def outer(self) -> Domain:
        """The outer domain, whose projection the whole set shares."""
        return self.domains[0]

    def __len__(self) -> int:
        return len(self.domains)

    def __iter__(self):
        return iter(self.domains)

    def grid_cells(self) -> list[tuple[int, int]]:
        """
        Each domain's size in cells, (south-north, west-east), as in its geo_em.

        One less than `e_sn` and `e_we`, which count the staggered grid.
        """
        return [(domain.geometry.e_sn - 1, domain.geometry.e_we - 1) for domain in self.domains]

    def per_domain(self, attribute: str) -> list:
        """One value of a `Domain` or `DomainGeometry` attribute per domain, in WRF order."""
        return [
            getattr(domain, attribute)
            if hasattr(domain, attribute)
            else getattr(domain.geometry, attribute)
            for domain in self.domains
        ]
