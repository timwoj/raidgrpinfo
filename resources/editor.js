var nrealm = null;
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

function formSubmit(e) {
    console.log("submit");
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
        
        console.log(name);
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

    $("<input type='hidden' name='json'/>").val(data).appendTo("#toonform");
    $("#toonform").submit();
};

$(function(){
    $(".btnDelete").bind("click", Delete);
    $("#btnAdd").bind("click", Add);
    $(".changeRealm").bind("click", changeRealm);
    $("#realmSelect").bind("change", realmSelected);
    $("#realmCancel").bind("click", cancelSelect);
    $("#submit").bind("click", formSubmit);

    // there's probably a better way to do this, but use the HTML to build a
    // lookup table for the realm to normalized realm entries and store the
    // current local realm entry
    nrealm = $("#nrealm").val();
    $("#realmSelect > option").each(function() {
        nrealmToRealm[this.id] = this.value;
        realmToNRealm[this.value] = this.id;
    });
});
