from .. import Base
from .. import DBSession
import re
from sqlalchemy import and_, String

import gc
def find_subclasses(cls):
    all_refs = gc.get_referrers(cls)
    results = []
    for obj in all_refs:
        # __mro__ attributes are tuples
        # and if a tuple is found here, the given class is one of its members
        if (isinstance(obj, tuple) and
            # check if the found tuple is the __mro__ attribute of a class
            getattr(obj[0], "__mro__", None) is obj):
            results.append(obj[0])
    return results

class AlchemyBaseRest(object):
    DBClass = None
    collection_get_eager_load = []

    def filter(self):
        pass

    def order(self):
        pass

    def __init__(self, request):
        self.request = request

    def collection_get(self):
        """Returns a list of all object."""
        if 'filter' in self.request.params:
            db_objects = DBSession.query(self.DBClass). \
                filter(self.filter(self.request.params['filter'])). \
                order_by(self.order()).all()
        else:
            db_objects = DBSession.query(self.DBClass).order_by(self.order()).all()
        objects = []
        for o in db_objects:
            o._json_eager_load = self.collection_get_eager_load
            objects.append(o.to_dict())
        return objects

    def collection_post(self):
        """Adds a new user."""
        o = self.DBClass()
        o.from_dict(self.request.json)
        DBSession.add(o)
        # para obtener el id
        DBSession.flush()
        return {self.DBClass.__tablename__: o.to_dict()}

    def delete(self):
        """Removes the user."""
        o = DBSession.query(self.DBClass).filter_by(id=self.request.matchdict['id']).first()
        DBSession.delete(o)
        return {self.DBClass.__tablename__: o.to_dict()}

    def put(self):
        o = DBSession.query(self.DBClass).filter_by(id=self.request.matchdict['id']).first()
        for key in self.request.json:
            setattr(o, key, self.request.json[key])
        return {self.DBClass.__tablename__: o.to_dict()}

    def get(self):
        o = DBSession.query(self.DBClass).filter_by(id=self.request.matchdict['id']).first()
        return o.to_dict()
        #return {self.DBClass.__tablename__: object.to_dict()}

    def post(self):
        o = self.DBClass()
        o.from_dict(self.request.json)
        DBSession.merge(o)
        return self.request.json


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
                attr_class = {k.upper(): v for k, v in globals().items()}[fs[0].upper()]
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
