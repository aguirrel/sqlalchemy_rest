from datetime import date, time, datetime

def from_dict(self, values):
    """Merge in items in the values dict into our object if it's one of our columns
    """
    json_eager_save = set(getattr(self, '_json_eager_save', []))

    for c in self.__table__.columns:
        if c.name in values:
            setattr(self, c.name, values[c.name])

    for c in json_eager_save:
        if c in values and values[c] is not None:
            attr = getattr(self, c)
            attr_class = getattr(self.__class__, c).property.mapper.class_
            if isinstance(attr, list):
                for x in values[c]:
                    i = attr_class()
                    i.from_dict(x)
                    attr.append(i)
            else:
                if c in values is not None:
                    attr = attr_class()
                    attr.from_dict(values[c])
            setattr(self, c, attr)


dthandler = lambda obj: (obj.isoformat() if isinstance(obj, datetime.datetime) or isinstance(obj, datetime.date) else obj)


def to_dict(self):
    """
    Converts all the properties of the object into a dict for use in json.
    You can define the following in your class

    _json_eager_load :
        list of which child classes need to be eagerly loaded. This applies
        to one-to-many relationships defined in SQLAlchemy classes.

    _base_blacklist :
        top level blacklist list of which properties not to include in JSON

    _json_blacklist :
        blacklist list of which properties not to include in JSON

    :param request: Pyramid Request object
    :type request: <Request>
    :return: dictionary ready to be jsonified
    :rtype: <dict>
    """

    props = {}

    # grab the json_eager_load set, if it exists
    # use set for easy 'in' lookups
    json_eager_load = set(getattr(self, '_json_eager_load', []))
    # now load the property if it exists
    # (does this issue too many SQL statements?)
    for prop in json_eager_load:
        getattr(self, prop, None)

    # we make a copy because the dict will change if the database
    # is updated / flushed
    options = self.__dict__.copy()

    # setup the blacklist
    # use set for easy 'in' lookups
    blacklist = set(getattr(self, '_base_blacklist', []))
    # extend the base blacklist with the json blacklist
    blacklist.update(getattr(self, '_json_blacklist', []))

    for key in options:
        # skip blacklisted, private and SQLAlchemy properties
        if key in blacklist or key.startswith(('__', '_sa_', '_')):
            continue

        # format and date/datetime/time properties to isoformat
        obj = getattr(self, key)
        if isinstance(obj, (datetime, date, time)):
            props[key] = obj.isoformat()
            #props[key] = mktime(obj.timetuple()) * 1000
        else:
            # get the class property value
            attr = getattr(self, key)
            # let see if we need to eagerly load it
            if key in json_eager_load:
                # this is for SQLAlchemy foreign key fields that
                # indicate with one-to-many relationships
                if not hasattr(attr, 'pk') and attr:
                    # jsonify all child objects
                    if isinstance(attr, list):
                        attr = [x.to_dict() for x in attr]
                    else:
                        attr = attr.to_dict()
            else:
                # convert all non integer strings to string or if
                # string conversion is not possible, convert it to
                # Unicode
                if attr and not isinstance(attr, (int, float)):
                    try:
                        attr = str(attr)
                    except UnicodeEncodeError:
                        attr = attr.encode('utf-8')

            props[key] = attr

    return props
