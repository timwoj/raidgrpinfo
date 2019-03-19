import Noty from 'noty';
import PlainModal from 'plain-modal';

var nrealm = null;
var ngroup = null;

var realmToNRealm = {};
var nrealmToRealm = {};

function Delete(event){
    // event.preventDefault();
    // event.stopPropagation();
    
    // TODO: confirmation box appears n-1 times where n is the number of toons
    // on the page.  no idea why it does that.
    let par = $(this).parent().parent(); // tr
    // // the jquery noob in me says there *has* to be a different way to do this
    // let toon = par.children().first().children().first().val();
    // let r = confirm("Delete toon '"+toon+"'?");
    // if (r == true)
    // {
        par.remove();
        return true;
    // }
    // return r;
};

function Add(){
    $("#membersTable tbody").append(
	"<tr style='font-size:14px;padding:2px 5px;text-align:center'>"+
            "<td><input type='text' accept-charset='UTF-8' style='text-transform: none;'/></td>"+
            "<td><select>"+
            "<option value='tank'>Tank</option>"+
            "<option value='healer'>Healer</option>"+
            "<option value='dps' selected>Melee DPS</option>"+
            "<option value='ranged'>Ranged DPS</option>"+
            "</select></td>"+
            "<td><select>"+
            "<option value='main'>Main</option>"+
            "<option value='bench'>Bench</option>"+
            "<option value='alt'>Alt</option>"+
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
  lastClicked = e.currentTarget;

  const modal = new PlainModal(document.getElementById('realmWindow'), {duration: 0});
  modal.show();
};

function authPw() {
    // validate the password before doing anything else
    let pw=$("#pw").val();
    let data='group='+ngroup+'&realm='+nrealm+'&pw='+pw;

    $.post('/val', data)
        .done(function() {
            console.log('password authentication success');
            postdata();
        })
        .fail(function() {
          console.log('password authentication failed');
          new Noty({
            type: 'error',
            text: 'Password is invalid!',
            timeout: 4000
          });
        });
    return false;
}

function postdata() {
    let url = '/'+nrealm+'/'+ngroup;

    let groupname = $('#group').val();
    let pw = $('#pw').val();
    let json = buildjson();
    
    let data = 'group='+groupname+'&json='+json+'&pw='+pw;

    $.post(url, data)
        .done(function() {
            window.location.replace(url);
        })
        .fail(function() {
            console.log('setting group data failed');
        });
}

function buildjson() {

    let data = {toons: []};

    // using the DOM table implementation here because it's a bit more
    // readable.  this could be changed to use jquery later.
    let body = document.getElementById('tablebody');
    let rowCount = body.rows.length;
    for (let i=0; i<rowCount; i+=1) {
        let row = body.rows[i];
        let name = row.cells[0].childNodes[0].value.trim();

        // if the name field is empty, just skip this toon
        if (name.length == 0) {
            continue;
        }

        name = name.toLowerCase();
        if (name.charCodeAt(0) < 128) {
            name = name.charAt(0).toUpperCase() + name.slice(1);
        }

        let realm = row.cells[3].childNodes[0].textContent;
        realm = realmToNRealm[realm];

        toon = {
            name: name,
            role: row.cells[1].childNodes[0].value.toLowerCase(),
            status: row.cells[2].childNodes[0].value.toLowerCase(),
            realm: realm
        };

        data['toons'].push(toon);
    }

    return JSON.stringify(data);
}

function normalize_gn(groupname)
{
    let norm = groupname.replace("'","");
    norm = norm.replace(" ", "-");
    norm = norm.toLowerCase();
    return norm;
}

$(function(){
    $(".btnDelete").bind("click", Delete);
    $("#btnAdd").bind("click", Add);
    $(".changeRealm").bind("click", changeRealm);
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

    $("#realmWindow").jqxWindow({
        maxHeight: 150, maxWidth: 280, minHeight: 30, minWidth: 250, height: 100, width: 270,
        isModal: true, okButton: $("#realmOK"), cancelButton: $("#realmCancel"),
        resizable: false, autoOpen: false, showCloseButton: false,
    });

    $("#realmWindow").on('close', function(event) {
        if (event.args.dialogResult.OK) {
            lastClicked.textContent = $("#realmSelect").val();
        }
    });
});
