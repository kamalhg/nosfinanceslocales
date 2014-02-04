# -*- coding: utf-8 -*-

import re
import json
import os
import numpy as np
import brewer2mpl
from sqlalchemy import func, cast, Float, select, alias, and_
from sqlalchemy.sql import compiler
from psycopg2.extensions import adapt as sqlescape


from .models import DBSession, AdminZone, AdminZoneFinance, Stats, SRID, ADMIN_LEVEL_CITY

POP_VAR = cast(AdminZoneFinance.data['population'], Float)

MAPS_CONFIG = {
    'charges-financieres-par-habitant': {
        'description': u'Charges financières annuelles par habitant (en €)',
        'sql_variable': cast(AdminZoneFinance.data['financial_costs'], Float) / POP_VAR,
        'sql_filter': and_(POP_VAR > 0, AdminZoneFinance.data['financial_costs'] <> 'nan'),
        'colors': lambda size: brewer2mpl.get_map('YlGnBu', 'Sequential', size)
    },
    'taxe-fonciere': {
        'description': u'Taxe foncière (en %)',
        'sql_variable': 100*cast(AdminZoneFinance.data['property_tax_rate'], Float),
        'sql_filter': AdminZoneFinance.data['property_tax_rate'] <> 'nan',
        'colors': lambda size: brewer2mpl.get_map('YlOrRd', 'Sequential', size)
    },
    'taxe-habitation': {
        'description': u'Taxe d\'habitation (en %)',
        'sql_variable': 100*cast(AdminZoneFinance.data['home_tax_rate'], Float),
        'sql_filter': AdminZoneFinance.data['home_tax_rate'] <> 'nan',
        'colors': lambda size: brewer2mpl.get_map('PuRd', 'Sequential', size)
    },
    'produits-taxe-fonciere-par-habitant': {
        'description': u'Taxe foncière par habitant (en €)',
        'sql_variable': cast(AdminZoneFinance.data['property_tax_value'], Float) / POP_VAR,
        'sql_filter': and_(POP_VAR > 0, AdminZoneFinance.data['property_tax_value'] <> 'nan'),
        'colors': lambda size: brewer2mpl.get_map('OrRd', 'Sequential', size)
    },
    'produits-taxe-habitation-par-habitant': {
        'description': u'Taxe d\'habitation par habitant (en €)',
        'sql_variable': cast(AdminZoneFinance.data['home_tax_value'], Float) / POP_VAR,
        'sql_filter': and_(POP_VAR > 0, AdminZoneFinance.data['home_tax_value'] <> 'nan'),
        'colors': lambda size: brewer2mpl.get_map('BuPu', 'Sequential', size)
    },
    'produits-fonctionnement-par-habitant': {
        'description': u'Total des produits de fonctionnement par habitant (en €)',
        'sql_variable': cast(AdminZoneFinance.data['operating_revenues'], Float) / POP_VAR,
        'sql_filter': and_(POP_VAR > 0, AdminZoneFinance.data['operating_revenues'] <> 'nan'),
        'colors': lambda size: brewer2mpl.get_map('Spectral', 'Diverging', size)
    },
    'charges-fonctionnement-par-habitant': {
        'description': u'Total des charges de fonctionnement par habitant (en €)',
        'sql_variable': cast(AdminZoneFinance.data['operating_costs'], Float) / POP_VAR,
        'sql_filter': and_(POP_VAR > 0, AdminZoneFinance.data['operating_costs'] <> 'nan'),
        'colors': lambda size: brewer2mpl.get_map('BrBG', 'Diverging', size),
    },
    'emplois-investissements-par-habitant': {
        'description': u"Total des emplois d'investissements par habitant (en €)",
        'sql_variable': cast(AdminZoneFinance.data['investments_usage'], Float) / POP_VAR,
        'sql_filter': and_(POP_VAR > 0, AdminZoneFinance.data['investments_usage'] <> 'nan'),
        'colors': lambda size: brewer2mpl.get_map('RdYlBu', 'Diverging', size),
    },
    'annuite-dette-par-habitant': {
        'description': u'Annuité de la dette par habitant (en €)',
        'sql_variable': cast(AdminZoneFinance.data['debt_annual_costs'], Float) / POP_VAR,
        'sql_filter': and_(POP_VAR > 0, AdminZoneFinance.data['debt_annual_costs'] <> 'nan'),
        'colors': lambda size: brewer2mpl.get_map('Spectral', 'Diverging', size),
    },
    'ressources-investissements-par-habitant': {
        'description': u"Total des ressources d'investissement par habitant (en €)",
        'sql_variable': cast(AdminZoneFinance.data['investment_ressources'], Float) / POP_VAR,
        'sql_filter': and_(POP_VAR > 0, AdminZoneFinance.data['investment_ressources'] <> 'nan'),
        'colors': lambda size: brewer2mpl.get_map('RdGy', 'Diverging', size),
    },
    'charges-personnel-par-habitant': {
        'description': u'Charges de personnel par habitant (en €)',
        'sql_variable': cast(AdminZoneFinance.data['staff_costs'], Float) / POP_VAR,
        'sql_filter': and_(POP_VAR > 0, AdminZoneFinance.data['staff_costs'] <> 'nan'),
        'colors': lambda size: brewer2mpl.get_map('Reds', 'Sequential', size),
    },
    'subventions-versee-par-habitant': {
        'description': u'Subventions versées par habitant (en €)',
        'sql_variable': cast(AdminZoneFinance.data['paid_subsidies'], Float) / POP_VAR,
        'sql_filter': and_(POP_VAR > 0, AdminZoneFinance.data['paid_subsidies'] <> 'nan'),
        'colors': lambda size: brewer2mpl.get_map('YlOrBr', 'Sequential', size),
    }
}

BORDERS_MSS = """
line-color: #eee;
  line-join: round;
  line-cap: round;
  polygon-gamma: 0.1;
  line-width: 0;
  [zoom>6][zoom<9] {
    line-width: 0.1;
  }
  [zoom=9] {
    line-width: 0.3;
  }
  [zoom=10] {
    line-width: 0.9;
  }
  [zoom=11] {
    line-width: 1.5;
  }
  [zoom>11] {
    line-width: 2.0;
  }
"""

def compile_query(query):
    """Hack function to get sql query with params"""
    dialect = query.session.bind.dialect
    statement = query.statement
    comp = compiler.SQLCompiler(dialect, statement)
    comp.compile()
    enc = dialect.encoding
    params = {}
    for k,v in comp.params.iteritems():
        if isinstance(v, unicode):
            v = v.encode(enc)
        params[k] = sqlescape(v)
    # XXX: hack to remove ST_AsBinary put by geoalchemy, it breaks mapnik query
    # :(((
    str_query = (comp.string.encode(enc) % params).decode(enc)
    m = re.search('ST_AsBinary\(([\w\.]*)\)', str_query)
    if len(m.groups()) > 1:
        # the trick does not handle this case
        raise
    return str_query.replace(m.group(), m.groups()[0])

def quantile_scale(sql_variable, sql_filter, size):
    values = map(float, zip(*DBSession.query(sql_variable).filter(sql_filter).all())[0])
    return np.percentile(values, list(np.linspace(0, 100, size+1)))

def get_extent():
    return DBSession.query(
        func.min(func.ST_XMin(AdminZone.geometry)),
        func.min(func.ST_YMin(AdminZone.geometry)),
        func.max(func.ST_XMax(AdminZone.geometry)),
        func.max(func.ST_YMax(AdminZone.geometry)),
    ).first()

def france_layer(layer_id, query):
    engine = DBSession.get_bind()
    datasource = {
        'type': 'postgis',
        'table': "(%s) as map_table" % query,
        'user': engine.url.username,
        'host': engine.url.host,
        'dbname': engine.url.database,
        'password': engine.url.password,
        'srid': SRID,
    }

    layer = {
        'name':layer_id, #useful ? keep name or id ?
        'id': layer_id,
        'geometry': 'polygon',
        'srs': '+proj=longlat +ellps=WGS84 +datum=WGS84 +no_defs',
        'Datasource': datasource,
    }
    return layer

def map_query(year, variable, variable_filter):
    q = DBSession.query(AdminZone.id, AdminZone.geometry, AdminZone.name, AdminZone.code_insee.label('code_insee'), AdminZoneFinance.year, variable)
    return compile_query(q.filter(AdminZoneFinance.year==year).filter(AdminZone.admin_level==ADMIN_LEVEL_CITY).filter(variable_filter).join(AdminZoneFinance, AdminZone.id==AdminZoneFinance.adminzone_id))

def scale_mss(layer, var_name, x, colors):
    styles = []
    def price_style(x_min, x_max, color):
        template = "[%(var_name)s>%(min)s][%(var_name)s<=%(max)s] { polygon-fill: %(color)s; line-color: %(color)s; }"
        return template % { 'var_name': var_name,
                            'min': x_min,
                            'max': x_max,
                            'color': color }
    for x_min, x_max, color in zip(x[:-1], x[1:], colors):
        styles.append(price_style(x_min, x_max, color) )
    return "#%s::variable{\n%s\n}"%(layer, '\n'.join(styles))

class Map(object):
    def __init__(self, year, name):
        variables = MAPS_CONFIG.get(name)
        query = map_query(year, variables['sql_variable'].label(name), variables['sql_filter'])
        layer = "layer_%s"%name

        # style
        # build scale based on quantiles
        size = 9
        stats = DBSession.query(Stats).filter(Stats.name==name).first()
        scale_range = json.loads(stats.data['scale'])
        assert size + 1 == len(scale_range)

        colors = variables['colors'](size).hex_colors

        self.info = {
            'description': variables['description'],
            'year': year,
            'name': name,
            'id': "%s_%s"%(name, year),
            'minzoom': 5,
            'maxzoom': 9,
            'scale_colors': colors,
            'scale_range': scale_range,
            'extent': list(get_extent()), # XXX: simplejson bug with sqlalchemy list, cast to python list to make it works
        }

        self.mapnik_config = {
            'srs': "+proj=merc +a=6378137 +b=6378137 +lat_ts=0.0 +lon_0=0.0 +x_0=0.0 +y_0=0.0 +k=1.0 +units=m +nadgrids=@null +wktext +no_defs +over",
            'Layer': [france_layer(layer, query)],
            'Stylesheet': [
                {'id': 'scale.mss', 'data': scale_mss(layer, name, scale_range, colors)},
                {'id': 'borders.mss', 'data': BORDERS_MSS},
            ],
        }

class TimeMapRegistry(dict):
    def __missing__(self, key):
        self[key] = [Map(year, key) for year in range(2000, 2013)]
        return self[key]

# cache timemap registry 'cause it's quite long to get it
from .cache import region
@region.cache_on_arguments(namespace="timemaps")
def create_timemap_registry():
    registry = TimeMapRegistry()
    for key in MAPS_CONFIG.keys():
        registry[key]
    return registry

timemap_registry = create_timemap_registry()
