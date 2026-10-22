// fe-backups.js — version history panel: lists field_backups rows created on
// each save/restore, lets the user restore an older version.
'use strict';

var FE = window.FE || (window.FE = {});

FE.backups = {};

FE.backups.updateList = function () {
    var el = document.getElementById('backupsList');
    if (!el) return;
    if (!FE.field) {
        el.innerHTML = '<div class="text-muted" style="font-size:0.85em;">Откройте поле</div>';
        return;
    }
    var name = FE.field.__name;
    FE.api.listBackups(name).then(function (list) {
        if (!list || !list.length) {
            el.innerHTML = '<div class="text-muted" style="font-size:0.85em;">Бэкапов пока нет (создаются при каждом сохранении)</div>';
            return;
        }
        var html = '';
        list.forEach(function (b) {
            var d = new Date((b.created || 0) * 1000);
            var when = ('0' + d.getDate()).slice(-2) + '.' + ('0' + (d.getMonth() + 1)).slice(-2) + ' ' +
                ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2) + ':' +
                ('0' + d.getSeconds()).slice(-2);
            html += '<div class="d-flex justify-content-between align-items-center" style="font-size:0.85em;padding:2px 0;border-bottom:1px solid #eee;">' +
                '<span>' + when + '</span>' +
                '<button class="btn btn-xs btn-outline-danger" style="padding:0 4px;font-size:0.75em;" ' +
                'onclick="FE.backups.restore(\'' + FE.escapeHtml(b.id) + '\')">Восстановить</button>' +
                '</div>';
        });
        el.innerHTML = html;
    }).catch(function (e) {
        el.innerHTML = '<div class="text-danger" style="font-size:0.85em;">Ошибка: ' + FE.escapeHtml(e.message) + '</div>';
    });
};

FE.backups.restore = function (backupId) {
    if (!FE.field) return;
    if (!window.confirm('Восстановить эту версию? Текущее содержимое будет сохранено в бэкап.')) return;
    var name = FE.field.__name;
    FE.api.restoreBackup(name, backupId).then(function (res) {
        FE.status('Версия восстановлена, перезагрузка...');
        FE.dirty = false;
        return FE.openField(name, res.updated);
    }).then(function () {
        FE.status('Версия восстановлена');
        FE.backups.updateList();
    }).catch(function (e) {
        alert('Ошибка восстановления: ' + e.message);
    });
};

FE.backups.init = function () {
    document.getElementById('btnBackupsRefresh').addEventListener('click', FE.backups.updateList);
    FE.hooks.afterOpen.push(function () { FE.backups.updateList(); });
    FE.hooks.afterClose.push(function () { FE.backups.updateList(); });
};
