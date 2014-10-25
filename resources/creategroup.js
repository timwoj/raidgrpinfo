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
        
        // clear the text field
        newtoon.value = "";
    }
}

function removeFromList()
{
    var toons = document.getElementById("toons");
    toons.remove(toons.selectedIndex);
}

function selectAllToons()
{
    var selObj = document.getElementById("toons");
    for (var i=0; i<selObj.options.length; i++) {
        selObj.options[i].selected = true;
    }
}
