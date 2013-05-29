function togglePanelStatus(id)
{
    // Get the element by ID from the dom
    var elem = document.getElementById("slots"+id);
    
    // Set the element to be displayed or hidden
    var expand = (elem.style.display=="none");
    elem.style.display = (expand ? "block" : "none");
    
    // Turn the arrow based on whether the block is hidden or not
    imgelem = document.getElementById("slotsimg"+id);
    imgelem.src = imgelem.src
    .split(expand ? "right.png" : "down.png")
    .join(expand ? "down.png" : "right.png");
}
