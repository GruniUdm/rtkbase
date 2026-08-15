function actionFormatter (value,row,index) {
    
    return value
}

const createRinexBtnElt = document.getElementById('create-rinex-button');

window.operateEvents = {
    'click #log_delete': function (e, value, row, index) {
        document.querySelector('#filename').textContent = row.name;
        $('#deleteModal').modal();
        $('#confirm-delete-button').data.row = row;
    },
    'click #log_edit': function(e, value, row, index) {
        document.querySelector('#filename').textContent = row.name;
        if ( row.format.split(".").pop() === "ZIP") {
            createRinexBtnElt.removeAttribute('disabled');
        }
        else {
            createRinexBtnElt.setAttribute('disabled', '');
        }
        $('#editModal').modal();
        createRinexBtnElt.dataset.filename = row.name;
    }
};

$('#confirm-delete-button').on("click", function (){
    socket.emit("delete log", $('#confirm-delete-button').data.row);
});

createRinexBtnElt.onclick = function (){
    socket.emit("rinex conversion", {"filename": createRinexBtnElt.dataset.filename, "rinex-preset" : document.querySelector("#editModal a.active").dataset.rinexPreset});
    $(this).html('<span class="spinner-border spinner-border-sm"></span> Creating Rinex...');
    document.getElementById("rinex-conversion-msg").replaceChildren();
};

$(document).ready(function () {

    namespace = "/test";
    socket = io.connect(namespace);

    socket.on("connect", function () {
        socket.emit("browser connected", {data: "I'm connected"});
    });

    socket.emit("get logs list");

    socket.on('disconnect', function(){
        console.log('disconnected');
    });

    $("#editModal").on('hidden.bs.modal', function(){
        socket.emit("get logs list");
        var failedTitleElt = document.getElementById("failed_title");
        if (failedTitleElt != null) {
            failedTitleElt.remove();
        };
        var failedMsgElt = document.getElementById("failed_msg");
        if (failedMsgElt != null) {
            failedMsgElt.remove();
        };
        document.getElementById("rinex-conversion-msg").replaceChildren();
        $('#create-rinex-button').html('Create Rinex file');
      });

       // ################" TABLE ##########################"

    socket.on('available logs', function(msg){
        
        var actionDownloadElt = document.createElement("a");
        actionDownloadElt.href = "#";
        actionDownloadElt.setAttribute("title", "download");
        actionDownloadElt.setAttribute("id", "log_download")
        actionDownloadElt.classList.add("mx-1");
            var downloadImg = document.createElement("img");
            downloadImg.setAttribute("src", "../static/images/download.svg");
            downloadImg.setAttribute("alt", "download");
            downloadImg.setAttribute("title", "Download");
            downloadImg.setAttribute("width", "25");
            downloadImg.setAttribute("height", "25");
        actionDownloadElt.appendChild(downloadImg);

        var actionEditElt = document.createElement("a");
        actionEditElt.href = "#";
        actionEditElt.setAttribute("title", "edit");
        actionEditElt.setAttribute("id", "log_edit")
        actionEditElt.classList.add("mx-1");
            var editImg = document.createElement("img");
            editImg.setAttribute("src", "../static/images/pencil.svg");
            editImg.setAttribute("alt", "edit");
            editImg.setAttribute("title", "Convert to Rinex");
            editImg.setAttribute("width", "25");
            editImg.setAttribute("height", "25");
        actionEditElt.appendChild(editImg);

        var actionDeleteElt = document.createElement("a");
        actionDeleteElt.href = "#";
        actionDeleteElt.setAttribute("title", "delete");
        actionDeleteElt.setAttribute("id", "log_delete");
        actionDeleteElt.setAttribute("data-toggle", "modal")
        actionDeleteElt.classList.add("mx-1");
            var deleteImg = document.createElement("img");
            deleteImg.setAttribute("src", "../static/images/trash.svg");
            deleteImg.setAttribute("alt", "delete");
            deleteImg.setAttribute("title", "Delete");
            deleteImg.setAttribute("width", "25");
            deleteImg.setAttribute("height", "25");
        actionDeleteElt.appendChild(deleteImg);

        for (log of msg) {
            actionDownloadElt.href = "/logs/download/" + log.name
            if (log.format === "TRACK") {
                var ip = log.name.replace("tracks/", "").replace(".csv", "");
                var m = ip.match(/^(.+?)_\d{8}_\d{6}$/);
                if (m) { ip = m[1]; } else { ip = ip.replace(/_/g, "."); }
                var cb = document.createElement("input");
                cb.type = "checkbox";
                cb.className = "mx-1 track-cb";
                cb.title = "Show on map";
                cb.setAttribute('data-ip', ip);
                var stored = [];
                try { stored = JSON.parse(localStorage.getItem("tractor_tracks_show") || "[]"); } catch(e) {}
                if (stored.indexOf(ip) !== -1) cb.setAttribute('checked', '');
                log['actions'] = cb.outerHTML + actionDownloadElt.outerHTML + actionDeleteElt.outerHTML;
            } else {
                log['actions'] = actionDownloadElt.outerHTML + actionEditElt.outerHTML + actionDeleteElt.outerHTML;
            }
        }

        $('#logtable').bootstrapTable('removeAll');
        $('#logtable').bootstrapTable('load', msg);
        })

    $(document).on('change', '.track-cb', function() {
        var ip2 = this.getAttribute('data-ip');
        if (!ip2) return;
        var stored = [];
        try { stored = JSON.parse(localStorage.getItem("tractor_tracks_show") || "[]"); } catch(e) {}
        if (this.checked) {
            if (stored.indexOf(ip2) === -1) stored.push(ip2);
        } else {
            stored = stored.filter(function(i) { return i !== ip2; });
        }
        try { localStorage.setItem("tractor_tracks_show", JSON.stringify(stored)); } catch(e) {}
    });

       // ################" SOCKETS ##########################"
   
       function downloadURI(uri, name) {
            var link = document.createElement("a");
            link.setAttribute('download', name);
            link.href = uri;
            document.body.appendChild(link);
            link.click();
            link.remove();
            };

        socket.on('rinex ready', function(msg){
        response = JSON.parse(msg);
        console.log(response);
        if (response.result == "success") {           
            $('#create-rinex-button').html('Create Rinex file');
            const SuccessTitleElt = document.createElement("h5");
            SuccessTitleElt.classList.add("text-success");
            SuccessTitleElt.textContent = "Success!";
            SuccessTitleElt.id = "success_title";
            $('#rinex-conversion-msg').append(SuccessTitleElt);

            const SuccessElt = document.createElement("p");
            SuccessElt.classList.add("text-left");
            SuccessElt.appendChild(document.createTextNode("Your Rinex file is ready "));
            var rinexDownBtnElt = document.createElement("a");
            rinexDownBtnElt.text = "Download it!";
            rinexDownBtnElt.setAttribute("title", "download rinex file");
            rinexDownBtnElt.classList.add("btn", "btn-primary");
            rinexDownBtnElt.id="download-rinex-btn";
            SuccessElt.appendChild(rinexDownBtnElt);
            SuccessElt.id = "success_msg";
            $('#rinex-conversion-msg').append(SuccessElt);
            rinexDownBtnElt.onclick = function (){
                var link = document.createElement("a");
                link.setAttribute('download', '');
                link.href = "/logs/download/" + response.file;
                document.body.appendChild(link);
                link.click();
                link.remove();
            }       
        }
        else if (response.result == "failed") {
            $('#create-rinex-button').html('Create Rinex file');
            const failedTitleElt = document.createElement("h5");
            failedTitleElt.classList.add("text-danger");
            failedTitleElt.textContent = "Failed!";
            failedTitleElt.id = "failed_title";
            $('#rinex-conversion-msg').append(failedTitleElt);

            const failedElt = document.createElement("p");
            failedElt.classList.add("text-left");
            if (response.msg.includes("more than 1 file")) {
                failedElt.appendChild(document.createTextNode("There is more than 1 file in the archive you want to convert. The reason could be a power outage or a main service stop/start. Please try with an archive containing only one file"));
                failedElt.id = "failed_msg";
            };
            $('#rinex-conversion-msg').append(failedElt);
        };
    });

})
