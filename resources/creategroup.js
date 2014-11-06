function addToList()
{
    // get the list, the text box, and the text from the box
    var toons = document.getElementById("toons");
    var newtoon = document.getElementById("newtoon");
    var toonname = newtoon.value.trim();

    if ((toonname.length <= 1) || (toonname.length > 30))
    {
        alert("Invalid toon name.  Must be between 2 and 30 characters long")
    }
    else
    {
        var existing = document.getElementById("opt"+toonname)
        if (existing == null)
        {
            var newopt = new Option(toonname, toonname)
            newopt.setAttribute("id", "opt"+toonname)
            toons.add(newopt, null)
        }
        
        var subCheck = document.getElementById("sub");
        var subfield = document.getElementById("subfield");
        var subArray;
        if (subfield.value != undefined && subfield.value.length != 0) {
            subArray = subfield.value.split(",");
        }
        else {
            subArray = new Array();
        }
        if (subCheck.checked)
        {
            subArray.push("1");
        }
        else
        {
            subArray.push("0");
        }
        subfield.value = subArray.join(",");

        var crCheck = document.getElementById("crossrealm");
        var crfield = document.getElementById("crfield");
        var crArray;
        if (crfield.value != undefined && crfield.value.length != 0) {
            crArray = crfield.value.split(",");
        }
        else {
            crArray = new Array();
        }
        if (crCheck.checked)
        {
            var realm = document.getElementById("realm");
            var chosenRealm = realm.options[realm.selectedIndex].id;
            crArray.push(chosenRealm);
        }
        else
        {
            crArray.push("0");
        }
        crfield.value = crArray.join(",");

        // reset the form fields so another toon can be added
        newtoon.value = "";
        sub.checked = false;
        crCheck.checked = false;
    }
}

function removeFromList()
{
    var toons = document.getElementById("toons");
    var index = toons.selectedIndex;
    while (index != -1) {
        toons.remove(index);
        
        var subfield = document.getElementById("subfield")
        if (subfield != undefined) {
            subArray = subfield.value.split(",");
            subArray.splice(index, 1);
            subfield.value = subArray.join();
        }
        
        var crfield = document.getElementById("crfield");
        if (crfield != undefined) {
            crArray = crfield.value.split(",");
            crArray.splice(index, 1);
            crfield.value = crArray.join();
        }

        index = toons.selectedIndex;
    }
}

function selectAllToons()
{
    var selObj = document.getElementById("toons");
    for (var i=0; i<selObj.options.length; i++) {
        selObj.options[i].selected = true;
    }
}

function crossRealmClicked(cb)
{
    var realms = document.getElementById("realm");
    if (cb.checked)
        realm.disabled = false;
    else
        realm.disabled = true;
}
