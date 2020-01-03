# -*- coding: utf-8 -*-
#!/usr/bin/env python

import json
from datetime import datetime

from flask import render_template, redirect
import wowapi

from google.appengine.ext import ndb
from google.appengine.api import memcache
from passlib.hash import sha256_crypt

# Minimum ilvls and colors for the ilvl grid
MIN_NORMAL = 445
MIN_HEROIC = 460
MIN_MYTHIC = 475
COLOR_LFR = '#FFB2B2'
COLOR_NORMAL = '#FFFFB2'
COLOR_HEROIC = '#B2FFB2'
COLOR_MYTHIC = '#C3BEFF'
COLOR_LEGENDARY = '#FFCA68'

CLASS_INDEXES = {
    'Warrior': 1,
    'Paladin': 2,
    'Hunter': 3,
    'Rogue': 4,
    'Priest': 5,
    'Death Knight': 6,
    'Shaman': 7,
    'Mage': 8,
    'Warlock': 9,
    'Monk': 10,
    'Druid': 11,
    'Demon Hunter': 12
}

# This is used to color the table cells on the grid display based on the ilvl
# of the item.  It gets put into the jinja environment as a filter.
def ilvlcolor(ilvl, quality):
    retval = ''
    if quality == 5:
        retval = 'background-color:'+COLOR_LEGENDARY
    elif ilvl > 0 and ilvl < MIN_NORMAL:
        retval = 'background-color:'+COLOR_LFR
    elif ilvl >= MIN_NORMAL and ilvl < MIN_HEROIC:
        retval = 'background-color:'+COLOR_NORMAL
    elif ilvl >= MIN_HEROIC and ilvl < MIN_MYTHIC:
        retval = 'background-color:'+COLOR_HEROIC
    elif ilvl >= MIN_MYTHIC:
        retval = 'background-color:'+COLOR_MYTHIC
    return retval

def normalize(groupname):
    return groupname.lower().replace('\'', '').replace(' ', '-')

def build_wowhead_rel(item, player_class):

    rel_entries = []

    bonus_lists = item.get('bonusLists', [])
    if bonus_lists:
        rel_entries.append('bonus=%s' % ':'.join(map(str, bonus_lists)))

    tooltips = item.get('tooltips', {})
    if tooltips.get('enchant', ''):
        rel_entries.append('ench=%s' % tooltips['enchant'])

    if tooltips.get('gems', ''):
        rel_entries.append('gems=%s' % tooltips['gems'])

    if tooltips.get('set', ''):
        rel_entries.append('pcs=%s' % tooltips['set'])

    azerite_ids = item.get('azerite', [])
    if azerite_ids:
        powers = [CLASS_INDEXES[player_class]] + [x for x in azerite_ids if x != 0]
        rel_entries.append('azerite-powers=%s' % ':'.join(map(str, powers)))

    azerite_ids = item.get('azerite', [])
    if azerite_ids:
        powers = [CLASS_INDEXES[player_class]] + [x for x in azerite_ids if x != 0]
        rel_entries.append('azerite-powers=%s' % ':'.join(map(str, powers)))

    return '&'.join(rel_entries)

class Toonv2(ndb.Model):
    name = ndb.StringProperty(indexed=True)
    role = ndb.StringProperty()
    main = ndb.BooleanProperty()
    realm = ndb.StringProperty()
    status = ndb.StringProperty()

class Groupv2(ndb.Model):
    nrealm = ndb.StringProperty(indexed=True)
    ngroup = ndb.StringProperty(indexed=True)
    groupname = ndb.StringProperty()
    password = ndb.StringProperty()
    toons = ndb.StructuredProperty(Toonv2, repeated=True)
    lastvisited = ndb.DateTimeProperty()

    @staticmethod
    def normalize(realm):
        return realm.lower().replace('\'', '').replace(' ', '-')

    @classmethod
    def query_group(cls, nrealm, ngroup):
        results = memcache.get('%s_%s' % (nrealm, ngroup))
        if results is None:
            print('group was not in memcache')
            group_result = cls.query(cls.nrealm == nrealm, cls.ngroup == ngroup).fetch(1)

            if group_result:
                print('found group in datastore, adding to memcache')
                results = group_result[0]
                memcache.set('%s_%s' % (nrealm, ngroup), results)
            else:
                print('group was not in datastore either')

        return results

def edit_group(nrealm, ngroup):

    # load the list of realms from the datastore that was loaded by the
    # /loadrealms service
    realms = wowapi.Realm.query(namespace='Realms').fetch()

    # try to load the group info from the database
    results = Groupv2.query_group(nrealm, ngroup)

    # Loop through the results from the data store and create a list
    # of toon names, the markers for subs, and the markers for
    # cross-realm.  If there weren't any results, blank lists will be
    # passed to the template.
    toons = []
    if results is not None:
        for toon in results.toons:
            newtoon = {
                'name': toon.name,
                'role': toon.role,
                'status': toon.status,
                'realm': str([x.realm for x in realms if x.slug == toon.realm][0])
            }

            toons.append(newtoon)

    # throw them at jinja to generate the actual html
    template_values = {
        'group': ngroup,
        'nrealm': nrealm,
        'realm': str([x.realm for x in realms if x.slug == nrealm][0]),
        'toons': toons,
        'realms': realms,
    }

    output = render_template('editor.html', **template_values)
    output += render_template('pagefooter.html')
    return output

def get_group(nrealm, ngroup):

    # try to load the group info from the database
    results = Groupv2.query_group(nrealm, ngroup)

    # if the group doesn't exist, drop into the interface to make a new
    # group
    if results is None:
        return redirect('/edit/%s/%s' % (nrealm, ngroup))

    # if the group exists, load the group from the blizzard API and display
    # it.
    results.lastvisited = datetime.now()
    results.put()
    return load_group(results)

def post_group(request, nrealm, ngroup):

    # try to load the group info from the database.  this is only necessary
    # to get the password from the database to verify that it's correct.
    results = Groupv2.query_group(nrealm, ngroup)

    if results is not None and not sha256_crypt.verify(request.form.get('pw', ''), results.password):
        output = '<html><head><title>Password failure</title></head><body>'
        output += 'Password did not match for this group!<p/>'
        output += '<a href="javascript:history.back()">Go Back</a>\n'
        output += '</body></html>'
        return output, 401

    group = None
    if results != None:
        group = results
    else:
        group = Groupv2()

    group.nrealm = nrealm
    group.ngroup = ngroup
    group.groupname = request.form.get('group', '').strip()
    group.password = sha256_crypt.encrypt(request.form.get('pw', ''))

    # load the json data that includes the toon data
    jsondata = json.loads(request.form.get('json', '').strip())
    print('number of toons saved: %d' % len(jsondata['toons']))

    # clear the old toon information and recreate it from the data from
    # the form
    del group.toons[:]
    for j in jsondata['toons']:
        toon = Toonv2(**j)
        group.toons.append(toon)

    group.toons = sorted(group.toons, key=lambda s: s.name.lower())
    group.lastvisited = datetime.now()
    group.put()

    # put this group in the memcache too so that it can be loaded from
    # there instead of from the datastore every time. It will also be loaded
    # from the memcache after the redirect.
    memcache.set('%s_%s' % (nrealm, ngroup), group)

    # Return a good status so the javascript will redirect to the group page
    return "", 200

def load_group(results):

    response = ''

    # Query ndb for the full realm name based on the results
    realm_query = wowapi.Realm.query(wowapi.Realm.slug == results.nrealm, namespace='Realms')
    realm_result = realm_query.fetch()
    frealm = realm_result[0].realm

    query = wowapi.ClassEntry.query()
    res = query.fetch()

    classes = {}
    for cls in res:
        classes[cls.classId] = cls.name

    data = []
    groupstats = {
        'ilvlmains': 0,
        'totalilvl': 0,
        'totalilvleq': 0,
        'cloth': 0,
        'leather': 0,
        'mail': 0,
        'plate': 0,
        'ranged': 0,
        'melee': 0,
        'tanks': 0,
        'healers': 0
    }

    # Use the API importer to load the data for the group into a list of
    # entries for each toon.  We'll loop through this data to build up
    # the page once all of the fetches are finished.
    importer = wowapi.Importer()
    importer.load(results.nrealm, frealm, results.toons, data, groupstats)

    # Catch the case where no mains were found in the data so we don't
    # divide by zero
    if groupstats['ilvlmains'] == 0:
        avgilvl = 0
        avgeqp = 0
    else:
        avgilvl = groupstats['totalilvl'] / groupstats['ilvlmains']
        avgeqp = groupstats['totalilvleq'] / groupstats['ilvlmains']

    # Build the page header with the group name, realm, and ilvl stats
    template_values = {
        'group': results.groupname,
        'frealm': frealm,
        'ngroup': results.ngroup,
        'nrealm': results.nrealm,
        'groupavgilvl': avgilvl,
        'groupavgeqp': avgeqp,
        'toondata': data,
        'tankcount': groupstats['tanks'],
        'healercount': groupstats['healers'],
        'meleecount': groupstats['melee'],
        'rangedcount': groupstats['ranged'],
        'clothcount': groupstats['cloth'],
        'leathercount': groupstats['leather'],
        'mailcount': groupstats['mail'],
        'platecount': groupstats['plate']
    }

    response += render_template('groupinfo-header.html', **template_values)
    response += '        <hr style="width:90%;clear: both"/><br/>\n'
    response += render_template('groupinfo-gridheader.html', **template_values)
    response += '<tbody>\n'

    # Loop through the data twice here to display the separate sections,
    # but don't actually loop through all of the data.  The lambda filters
    # filter the character data down to just the parts that are needed
    # for each loop.
    for idx, char in enumerate(data):
        response += add_character(char, results, classes)

    response += '</table><p/>\n'
    template_values = {
        'min_normal': MIN_NORMAL,
        'min_heroic': MIN_HEROIC,
        'min_mythic': MIN_MYTHIC,
        'color_lfr': COLOR_LFR,
        'color_normal': COLOR_NORMAL,
        'color_heroic': COLOR_HEROIC,
        'color_mythic': COLOR_MYTHIC,
    }
    response += render_template('groupinfo-colorlegend.html', **template_values)
    response += render_template('pagefooter.html')

    return response, 200

# Generic method to add a character to the page response
def add_character(char, results, classes):

    if 'load_status' in char and char['load_status'] == 'nok':
        template_values = {
            'name': char['name'],
            'load_status': char['load_status'],
            'reason': char['reason'],
            'realm': char['toonrealm'],
            'frealm': char['toonfrealm'],
        }
    elif 'items' in char:

        itemslots = ['head', 'shoulder', 'chest', 'hands', 'legs', 'feet', 'neck',
                     'back', 'wrist', 'waist', 'finger1', 'finger2', 'trinket1',
                     'trinket2', 'mainHand', 'offHand']
        items = char['items']

        template_values = {
            'load_status': 'ok',
            'name': char['name'],
            'frealm': char['toonfrealm'],   # full realm name
            'nrealm': results.nrealm,  # realm for group
            'realm': char['toonrealm'],  # realm for toon (might not be == to nrealm)
            'guild': char['guild']['name'] if 'guild' in char else None,
            'class': classes[char['class']],
            'status': char['status'],
            'role': char['role'],
            'avgilvl': items['averageItemLevel'],
            'azeriteLevel': items.get('neck', {}).get('azeriteLevel', 0)
        }

        avgilvleq = 0
        numitems = 0
        for slot in itemslots:
            template_values[slot] = {
                'itemLevel': 0,
                'set': 'no'
            }

            if slot in items:
                # Count up the item levels and number of items as we go
                avgilvleq += items[slot]['itemLevel']
                numitems += 1

                azerite_ids = []
                if 'azeriteEmpoweredItem' in items[slot]:
                    for power in items[slot]['azeriteEmpoweredItem'].get('azeritePowers', []):
                        azerite_ids.append(power['id'])

                template_values[slot]['id'] = items[slot]['id']
                template_values[slot]['enchant'] = items[slot]['enchant']
                template_values[slot]['itemLevel'] = items[slot]['itemLevel']
                template_values[slot]['bonusLists'] = items[slot]['bonusLists']
                template_values[slot]['tooltips'] = items[slot]['tooltipParams']
                template_values[slot]['quality'] = items[slot]['quality']
                template_values[slot]['azerite'] = azerite_ids
                if items[slot]['context'] == 'trade-skill':
                    template_values[slot]['set'] = 'crafted'
                else:
                    template_values[slot]['set'] = 'no'

        # if there's no offhand, assume the main hand is a 2-hander and count it double per Blizzard iLvl formula.
        if (not 'offHand' in items) and ('mainHand' in items):
            avgilvleq += items['mainHand']['itemLevel']
            numitems += 1

        if numitems != 0:
            template_values['avgilvle'] = round(float(avgilvleq)/float(numitems), 1)

    else:

        template_values = {
            'name': char['name'],
            'load_status': 'nok',
            'reason': 'Unknown error retrieving data for %s.  Refresh to try again' % char['name'],
            'realm': char['toonrealm'],
            'frealm': char['toonfrealm'],
        }

    return render_template('groupinfo-gridtoon.html', **template_values)

def validate_password(request):
    ngroup = request.form['group']
    nrealm = request.form['realm']
    password = request.form.get('pw', None)
    newgn = request.form.get('newgn', None)

    if password != None:
        # check that the realm and group names are valid, as a safety
        # measure.
        if (nrealm is None or ngroup is None):
            return 'Invalid', 401

        # grab the group the datastore and try to validate the password
        results = Groupv2.query_group(nrealm, ngroup)

        if results != None:
            if not sha256_crypt.verify(password, results.password):
                return 'Invalid', 401
            return 'Valid', 200

        # This covers the case where a group is being added since
        # it won't be in the database yet.
        return 'Valid', 200

    elif newgn != None:
        results = Groupv2.query_group(nrealm, ngroup)

        if results != None:
            return 'Invalid', 401

    return 'Valid', 200
