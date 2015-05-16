var nrealm = null;
var ngroup = null;

function deleteGroup(event) {
    if (event.args.dialogResult.OK) {
        var pw1=$("#deletepw1").val();
        var pw2=$("#deletepw2").val();
        if (pw1 != pw2) {
            $("#pwmismatch").jqxNotification("open");
            $("#deleteQuestion").jqxWindow("open");
            return;
        }

        var data='group='+ngroup+'&realm='+nrealm+'&pw='+pw1;

        console.log('sending ' + data + ' to be validated');
        $.post('/val', data)
            .done(function() {
                console.log('password authentication succeeded');
                $.post('/delete',data)
                    .done(function() {
                        window.location.replace('/');
                        // redirect to the front page
                    });
            })
            .fail(function() {
                console.log('password authentication failed');
                $("#pwinvalid").jqxNotification("open");
                $("#deleteQuestion").jqxWindow("open");
            });
    }
}

function openDeleteWindow(e) {
    $("#deleteQuestion").jqxWindow("open");
}

$(document).ready(function() {
    nrealm = $("#nrealm").val();
    ngroup = $("#ngroup").val();

    $("#roster").tablesorter({
        // set forced sort on the third column to ensure that subs are always at the bottom
        sortForce: [[2,1]],
        // default sort order is by group (to fix the above force sorting), then avg equipped
        // (descending) and finally name (ascending)
        sortList: [[2,1],[3,1],[0,0]],
    });

    $("#deleteQuestion").jqxWindow({
        height: 150, width: 350,
        isModal: true, okButton: $("#deleteOK"), cancelButton: $("#deleteCancel"),
        resizable: false, autoOpen: false, showCloseButton: false,
    });

    $("#deleteQuestion").on('close', deleteGroup);
    
    $("#pwmismatch").jqxNotification({position: "top-right", autoClose: true,
                                      autoCloseDelay: 4000, template: "error"});
    $("#pwinvalid").jqxNotification({position: "top-right", autoClose: true,
                                     autoCloseDelay: 4000, template: "error"});

    $("#deleteButton").bind("click", openDeleteWindow);
});
