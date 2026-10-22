// fe-api.js — wrappers around the RTKBase field REST API.
'use strict';

var FE = window.FE || (window.FE = {});

FE.api = {
    listFields: function () {
        return fetch('/api/fields/list').then(function (r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        });
    },

    // Returns {name, updated, ...field json} — updated comes from the list
    // endpoint, so we merge it in for the optimistic lock.
    loadField: function (name, updated) {
        return fetch('/api/fields/' + encodeURIComponent(name) + '/export').then(function (r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        }).then(function (data) {
            data.__name = name;
            data.__updated = updated;
            return data;
        });
    },

    saveField: function (name, data, baseUpdated) {
        var copy = {};
        Object.keys(data).forEach(function (k) {
            if (k !== '__name' && k !== '__updated') copy[k] = data[k];
        });
        var payload = { data: copy, base_updated: baseUpdated };
        return fetch('/api/fields/' + encodeURIComponent(name), {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }).then(function (r) {
            return r.json().then(function (body) {
                if (!r.ok) {
                    var err = new Error(body.message || body.error || 'HTTP ' + r.status);
                    err.status = r.status;
                    err.body = body;
                    throw err;
                }
                return body;
            });
        });
    },

    listBackups: function (name) {
        return fetch('/api/fields/' + encodeURIComponent(name) + '/backups').then(function (r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        });
    },

    restoreBackup: function (name, backupId) {
        return fetch('/api/fields/' + encodeURIComponent(name) + '/restore/' + encodeURIComponent(backupId), {
            method: 'POST'
        }).then(function (r) {
            return r.json().then(function (body) {
                if (!r.ok) throw new Error(body.error || 'HTTP ' + r.status);
                return body;
            });
        });
    },

    deleteField: function (name) {
        return fetch('/api/fields/' + encodeURIComponent(name), { method: 'DELETE' });
    },

    // Create a new field from raw field JSON (split/combine). 409 if the
    // name already exists.
    createField: function (name, data) {
        return fetch('/api/fields/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, data: data })
        }).then(function (r) {
            return r.json().then(function (body) {
                if (!r.ok) {
                    var err = new Error(body.message || body.error || 'HTTP ' + r.status);
                    err.status = r.status;
                    throw err;
                }
                return body;
            });
        });
    }
};
