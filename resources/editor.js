var nrealm = null;
var ngroup = null;

var realmToNRealm = {};
var nrealmToRealm = {};

function Delete(event){
    // event.preventDefault();
    // event.stopPropagation();
    
    // TODO: confirmation box appears n-1 times where n is the number of toons
    // on the page.  no idea why it does that.
    var par = $(this).parent().parent(); // tr
    // // the jquery noob in me says there *has* to be a different way to do this
    // var toon = par.children().first().children().first().val();
    // var r = confirm("Delete toon '"+toon+"'?");
    // if (r == true)
    // {
        par.remove();
        return true;
    // }
    // return r;
};

function Add(){
    $("#membersTable tbody").append(
	"<tr>"+
            "<td><input type='text'/></td>"+
            "<td><select>"+
            "<option>Tank</option>"+
            "<option>Healer</option>"+
            "<option>DPS</option>"+
            "</select></td>"+
            "<td><select>"+
            "<option>Main</option>"+
            "<option>Bench</option>"+
            "</select></td>"+
            "<td><div class='changeRealm'>"+nrealmToRealm[nrealm]+"</div></td>"+
	    "<td><img src='/resources/delete.png' height='24' width='24' class='btnDelete'/></td>"+
	    "</tr>");

    // Recreate these bindings to include the fields from the new row
    $(".btnDelete").bind("click", Delete);
    $(".changeRealm").bind("click", changeRealm);
};

var lastClicked = null;
function changeRealm(e) {
    console.log("change realm");
    $("#realmSelectDiv").show();
    lastClicked = e.currentTarget;
};

function realmSelected(e) {
    lastClicked.textContent = $("#realmSelect").val();
    $("#realmSelectDiv").hide();
};

function cancelSelect() {
    $("#realmSelectDiv").hide();
};

function authPw() {
    console.log('authPw');
    // validate the password before doing anything else
    var pw=$("#pw").val();
    var data='group='+ngroup+'&realm='+nrealm+'&pw='+pw;

    $.post('/val', data)
        .done(function() {
            console.log('password authentication success');
            postdata();
        })
        .fail(function() {
            console.log('password authentication failed');
            $("#pwfailDiv").show();
            setTimeout('$("#pwfailDiv").fadeOut("slow");', 4000);
        });
    return false;
}

function postdata() {
    console.log('postdata');
    var url = '/'+nrealm+'/'+ngroup;
    console.log('url = ' + url);

    var groupname = $('#group').val();
    var pw = $('#pw').val();
    var json = buildjson();
    
    var data = 'group='+groupname+'&json='+json+'&pw='+pw;

    $.post(url, data)
        .done(function() {
            console.log('posting group data success');
            console.log('redirecting to ' + url);
            window.location.replace(url);
        })
        .fail(function() {
            console.log('setting group data failed');
        });
}

function buildjson() {
    var data = '{"toons": [';

    // using the DOM table implementation here because it's a bit more
    // readable.  this could be changed to use jquery later.
    var body = document.getElementById('tablebody');
    var rowCount = body.rows.length;
    for (var i=0; i<rowCount; i+=1) {
        var row = body.rows[i];
        var name = row.cells[0].childNodes[0].value.trim();

        // if the name field is empty, just skip this toon
        if (name.length == 0)
            continue;
        
        if (i != 0) {
            data += ',';
        }
        data += '{"name": "';
        data += name;
        data += '", "role": "';
        data += row.cells[1].childNodes[0].value.toLowerCase();
        data += '", "group": "';
        data += row.cells[2].childNodes[0].value.toLowerCase();
        data += '", "realm": "';
        var realm = row.cells[3].childNodes[0].textContent;
        data += realmToNRealm[realm];
        data += '"}';
    }
    data += "]}";

    return data;
}

function normalize_gn(groupname)
{
    var norm = groupname.replace("'","");
    norm = norm.replace(" ", "-");
    norm = norm.toLowerCase();
    return norm;
}

$(function(){
    $(".btnDelete").bind("click", Delete);
    $("#btnAdd").bind("click", Add);
    $(".changeRealm").bind("click", changeRealm);
    $("#realmSelect").bind("change", realmSelected);
    $("#realmCancel").bind("click", cancelSelect);
    $("#submit").bind("click", authPw);

    // there's probably a better way to do this, but use the HTML to build a
    // lookup table for the realm to normalized realm entries and store the
    // current local realm entry
    nrealm = $("#nrealm").val();
    ngroup = $("#ngroup").val();
    $("#realmSelect > option").each(function() {
        nrealmToRealm[this.id] = this.value;
        realmToNRealm[this.value] = this.id;
    });
});
