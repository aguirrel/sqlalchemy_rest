from .. import Base
from .. import DBSession
import re
from sqlalchemy import and_, String, sql

import gc


def find_subclasses(cls):
    all_refs = gc.get_referrers(cls)
    results = []
    for obj in all_refs:
        # __mro__ attributes are tuples
        # and if a tuple is found here, the given class is one of its members
        if isinstance(obj, tuple) and getattr(obj[0], "__mro__", None) is obj:
            results.append(obj[0])
    return results


class AlchemyBase(object):
    DBClass = None
    DBCollectionFields = None
    DBGetFields = None
    max_count = 20

    def filter(self):
        pass

    def default_filter(self):
        return sql.true()

    def order(self):
        pass

    def __init__(self, request):
        self.request = request

    def collection_get(self):
        count = self.max_count
        page = 1

        if self.DBCollectionFields:
            db_query = DBSession.query(*self.DBCollectionFields).filter(self.default_filter())
        else:
            db_query = DBSession.query(self.DBClass).filter(self.default_filter())
        if 'filter' in self.request.params:
            db_query = db_query.filter(self.filter(self.request.params['filter']))
        if 'count' in self.request.params:
            count = int(self.request.params['count'])
            count = count if count <= max_count else max_count
        if 'page' in self.request.params:
            page = int(self.request.params['page'])

        db_objects = db_query.order_by(self.order()). \
            limit(count).offset((page - 1) * count). \
            all()
        return db_objects


    def collection_post(self):
        """Adds a new user."""
        o = self.DBClass()
        o.from_dict(self.request.json)
        DBSession.add(o)
        # para obtener el id
        DBSession.flush()
        return o.to_dict()

    def delete(self):
        """Removes the user."""
        o = DBSession.query(self.DBClass).filter_by(id=self.request.matchdict['id']).first()
        DBSession.delete(o)
        return o.to_dict()

    def put(self):
        o = DBSession.query(self.DBClass).filter_by(id=self.request.matchdict['id']).first()
        for key in self.request.json:
            setattr(o, key, self.request.json[key])
        return o.to_dict()

    def get(self):
        if self.DBGetFields:
            o = DBSession.query(*self.DBGetFields).filter_by(id=self.request.matchdict['id']).first()
        else:
            o = DBSession.query(self.DBClass).filter_by(id=self.request.matchdict['id']).first()
        return o
        # return {self.DBClass.__tablename__: object.to_dict()}

    def post(self):
        o = self.DBClass()
        o.from_dict(self.request.json)
        DBSession.merge(o)
        return self.request.json


class AlchemyBaseRest(AlchemyBase):
    collection_get_eager_load = []

    def collection_get(self):
        db_objects = super().collection_get()
        objects = []
        for o in db_objects:
            o._json_eager_load = self.collection_get_eager_load
            objects.append(o.to_dict())
        return objects

    def get(self):
        o = super().get()
        return o.to_dict()

class AlchemyBaseRestTable(AlchemyBaseRest):
    def filter(self):
        lfilters = []

        for f in self.filters:
            fs = f['field'].split('.')
            # Si es de un atributo compuesto
            if len(fs) > 1:
                attr_var = self.DBClass.__dict__[fs[0]]
                attr_class = {k.upper(): v for k, v in globals().items()}[fs[0].upper()]
                sub_attr_var = attr_class.__dict__[fs[1]]
                if type(sub_attr_var.property.columns[0].type) is String:
                    lfilters.append(attr_var.has(sub_attr_var.ilike(unaccent('%' + f['value'] + '%'))))
                else:
                    lfilters.append(attr_var.has(sub_attr_var == f['value']))
            else:
                attr_var = self.DBClass.__dict__[fs[0]]
                if type(attr_var.property.columns[0].type) is String:
                    lfilters.append(attr_var.ilike(unaccent('%' + f['value'] + '%')))
                else:
                    lfilters.append(attr_var == f['value'])

        return and_(*lfilters)

    def order(self):
        order = []

        if 'field' in self.order_by:
            fs = self.order_by['field'].split('.')

            if len(fs) > 1:
                attr_var = self.DBClass.__dict__[fs[0]]
                s = find_subclasses(Base)
                attr_class = {('%s' % c).split('\'')[1].split('.')[-1].upper(): c for c in s}[fs[0].upper()]
                sub_attr_var = attr_class.__dict__[fs[1]]
                order.append(getattr(sub_attr_var, self.order_by['value'])())
            else:
                attr_var = self.DBClass.__dict__[fs[0]]
                order.append(getattr(attr_var, self.order_by['value'])())

        return order

    def outerclass(self):
        cl = []

        if 'field' in self.order_by:
            fs = self.order_by['field'].split('.')
            if len(fs) > 1:
                s = find_subclasses(Base)
                cl.append({('%s' % c).split('\'')[1].split('.')[-1].upper(): c for c in s}[fs[0].upper()])
        return cl


    def collection_get(self):
        self.filters = []
        self.order_by = {}
        options = self.request.params
        order_by = dict()
        count = None
        page = None

        for k, v in options.items():
            if k == 'count':
                count = int(v)
            elif k == 'page':
                page = int(v)
            elif re.match(r'filter\[', k):
                self.filters.append({'field': re.split(r'\[(.*)\]', k)[1], 'value': v})
            elif re.match(r'sorting\[', k):
                self.order_by['field'] = re.split(r'\[(.*)\]', k)[1]
                self.order_by['value'] = v
            else:
                self.filters.append({'field': k, 'value': v})

        query = DBSession.query(self.DBClass).filter(self.filter())
        total = query.count()
        db_objects = query.outerjoin(*(self.outerclass())). \
            order_by(*(self.order())). \
            limit(count).offset((page - 1) * count). \
            all()

        objects = []
        for o in db_objects:
            o._json_eager_load = self.collection_get_eager_load
            objects.append(o.to_dict())
        ret = dict()
        ret['total'] = total
        ret['result'] = objects
        return ret
