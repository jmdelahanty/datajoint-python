import numpy as np
import logging
from . import DataJointError
from .relational import Relation

logger = logging.getLogger(__name__)


class Table(Relation):
    """
    A Table object is a relation associated with a table.
    A Table object provides insert and delete methods.
    Table objects are only used internally and for debugging.
    The table must already exist in the schema for its Table object to work.

    The table associated with an instance of Base is identified by its 'class name'.
    property, which is a string in CamelCase. The actual table name is obtained
    by converting className from CamelCase to underscore_separated_words and
    prefixing according to the table's role.

    Base instances obtain their table's heading by looking it up in the connection
    object. This ensures that Base instances contain the current table definition
    even after tables are modified after the instance is created.
    """

    def __init__(self, conn=None, dbname=None, class_name=None, definition=None):
        self.class_name = class_name
        self.conn = conn
        self.dbname = dbname
        self.conn.load_headings(self.dbname)

        if dbname not in self.conn.db_to_mod:
            # register with a fake module, enclosed in back quotes
            self.conn.bind('`{0}`'.format(dbname), dbname)

        #TODO: delay the loading until first use (move out of __init__)
        self.conn.load_headings()
        if self.class_name not in self.conn.table_names[self.dbname]:
            if definition is None:
                raise DataJointError('The table is not declared')
            else:
                declare(conn, definition, class_name)

    @property
    def sql(self):
        return self.full_table_name

    @property
    def heading(self):
        return self.conn.headings[self.dbname][self.table_name]

    @property
    def full_table_name(self):
        """
        :return: full name of the associated table
        """
        return '`%s`.`%s`' % (self.dbname, self.table_name)

    @property
    def table_name(self):
        """
        :return: name of the associated table
        """
        return self.conn.table_names[self.dbname][self.class_name]


    @property
    def full_class_name(self):
        """
        :return: full class name
        """
        return '{}.{}'.format(self.__module__, self.class_name)

    @property
    def primary_key(self):
        """
        :return: primary key of the table
        """
        return self.heading.primary_key

    def insert(self, tup, ignore_errors=False, replace=False):  # TODO: in progress (issue #8)
        """
        Insert one data tuple.

        :param tup: Data tuple. Can be an iterable in matching order, a dict with named fields, or an np.void.
        :param ignore_errors=False: Ignores errors if True.
        :param replace=False: Replaces data tuple if True.

        Example::

            b = djtest.Subject()
            b.insert(dict(subject_id = 7, species="mouse",\\
                           real_id = 1007, date_of_birth = "2014-09-01"))
        """
        # todo: do we support records and named tuples for tup?

        if issubclass(type(tup), tuple) or issubclass(type(tup), list):
            value_list = ','.join([repr(q) for q in tup])
            attribute_list = '`'+'`,`'.join(self.heading.names[0:len(tup)]) + '`'
        elif issubclass(type(tup), dict):
            value_list = ','.join([repr(tup[q])
                                  for q in self.heading.names if q in tup])
            attribute_list = '`' + '`,`'.join([q for q in self.heading.names if q in tup]) + '`'
        elif issubclass(type(tup), np.void):
            value_list = ','.join([repr(tup[q])
                                  for q in self.heading.names if q in tup])
            attribute_list = '`' + '`,`'.join(tup.dtype.fields) + '`'
        else:
            raise DataJointError('Datatype %s cannot be inserted' % type(tup))
        if replace:
            sql = 'REPLACE'
        elif ignore_errors:
            sql = 'INSERT IGNORE'
        else:
            sql = 'INSERT'
        sql += " INTO %s (%s) VALUES (%s)" % (self.full_table_name,
                                              attribute_list, value_list)
        logger.info(sql)
        self.conn.query(sql)

    def delete(self):   # TODO: (issues #14 and #15)
        pass

    def drop(self):
        """
        Drops the table associated to this object.
        """
        # TODO: make cascading (issue #16)
        self.conn.query('DROP TABLE %s' % self.full_table_name)
        self.conn.clear_dependencies(dbname=self.dbname)
        self.conn.load_headings(dbname=self.dbname, force=True)
        logger.debug("Dropped table %s" % self.full_table_name)

    def set_table_comment(self, comment):
        """
        Update the table comment in the table definition.

        :param comment: new comment as string

        """
        # TODO: add verification procedure (github issue #24)
        self.alter('COMMENT="%s"' % comment)

    def add_attribute(self, definition, after=None):
        """
        Add a new attribute to the table. A full line from the table definition
        is passed in as definition.

        The definition can specify where to place the new attribute. Use after=None
        to add the attribute as the first attribute or after='attribute' to place it
        after an existing attribute.

        :param definition: table definition
        :param after=None: After which attribute of the table the new attribute is inserted.
                           If None, the attribute is inserted in front.
        """
        position = ' FIRST' if after is None else (
            ' AFTER %s' % after if after else '')
        sql = self.field_to_sql(parse_attribute_definition(definition))
        self._alter('ADD COLUMN %s%s' % (sql[:-2], position))

    def drop_attribute(self, attr_name):
        """
        Drops the attribute attrName from this table.

        :param attr_name: Name of the attribute that is dropped.
        """
        self._alter('DROP COLUMN `%s`' % attr_name)

    def alter_attribute(self, attr_name, new_definition):
        """
        Alter the definition of the field attr_name in this table using the new definition.

        :param attr_name: field that is redefined
        :param new_definition: new definition of the field
        """
        sql = self.field_to_sql(parse_attribute_definition(new_definition))
        self._alter('CHANGE COLUMN `%s` %s' % (attr_name, sql[:-2]))

    def erd(self, subset=None, prog='dot'):
        """
        Plot the schema's entity relationship diagram (ERD).
        The layout programs can be 'dot' (default), 'neato', 'fdp', 'sfdp', 'circo', 'twopi'
        """
        if not subset:
            g = self.graph
        else:
            g = self.graph.copy()
        # todo: make erd work (github issue #7)
        """
         g = self.graph
         else:
         g = self.graph.copy()
         for i in g.nodes():
         if i not in subset:
         g.remove_node(i)
        def tablelist(tier):
        return [i for i in g if self.tables[i].tier==tier]

        pos=nx.graphviz_layout(g,prog=prog,args='')
        plt.figure(figsize=(8,8))
        nx.draw_networkx_edges(g, pos, alpha=0.3)
        nx.draw_networkx_nodes(g, pos, nodelist=tablelist('manual'),
        node_color='g', node_size=200, alpha=0.3)
        nx.draw_networkx_nodes(g, pos, nodelist=tablelist('computed'),
        node_color='r', node_size=200, alpha=0.3)
        nx.draw_networkx_nodes(g, pos, nodelist=tablelist('imported'),
        node_color='b', node_size=200, alpha=0.3)
        nx.draw_networkx_nodes(g, pos, nodelist=tablelist('lookup'),
        node_color='gray', node_size=120, alpha=0.3)
        nx.draw_networkx_labels(g, pos, nodelist = subset, font_weight='bold', font_size=9)
        nx.draw(g,pos,alpha=0,with_labels=false)
        plt.show()
        """

    def _alter(self, alter_statement):
        """
        Execute ALTER TABLE statement for this table. The schema
        will be reloaded within the connection object.

        :param alter_statement: alter statement
        """
        sql = 'ALTER TABLE %s %s' % (self.full_table_name, alter_statement)
        self.conn.query(sql)
        self.conn.load_headings(self.dbname, force=True)
        # TODO: place table definition sync mechanism