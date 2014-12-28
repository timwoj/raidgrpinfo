$(document).ready(function() {
    $("#roster").tablesorter({
        // set forced sort on the third column to ensure that subs are always at the bottom
        sortForce: [[2,0]],
        // default sort order is by group (to fix the above force sorting), then avg equipped
        // (descending) and finally name (ascending)
        sortList: [[2,0],[19,1],[0,0]],
    });
});
