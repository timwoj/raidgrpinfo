var nrealm = null;
var ngroup = null;

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
});
