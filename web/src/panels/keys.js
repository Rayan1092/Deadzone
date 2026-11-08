// No imports, so Node can test it.
// The H help popup: every key in a plain sentence, in four groups.
export const KEY_GROUPS = [
  { title: 'Run', keys: [
    ['Space', 'Start or pause the mission.'],
    ['+  −', 'Run the simulation faster or slower.'],
    ['⌫', 'Restart this scenario from the beginning.'],
    ['G', 'Show a short briefing written only from what reached the command post.'],
    ['Q', 'Show the codes for joining from a phone.'],
    ['X', 'Turn the sound cues on or off.'],
    ['H', 'Show or hide this help.'],
    ['Esc', 'Close whatever is open.'],
  ] },
  { title: 'View', keys: [
    ['0', 'See the whole building.'],
    ['1–9', 'Follow a robot (or click its chip or card).'],
    ['M', 'Switch between one view and the split view.'],
    ['C', 'One view: swap the command post map with the main view. Split view: look down on the command post.'],
    ['V', "Open the followed robot's camera."],
    ['D', 'Let the camera follow the action by itself.'],
    ['P', 'Use lighter graphics on a slower computer.'],
  ] },
  { title: 'Scenario', keys: [
    ['R', 'Drop rubble in front of the followed robot (Scout 1 if none).'],
    ['F', "Jam the followed robot's wheels."],
    ['O', "Overload the followed robot's computer."],
    ['U', 'Tell the followed robot to resume after a safety stop.'],
    ['A', 'Shake the building with an aftershock (Shift+A for a strong one).'],
    ['B', 'Show the same robots without Deadzone, then switch it back.'],
    ['N', 'Load a different building (Shift+N goes back to the main scenario).'],
  ] },
  { title: 'Model & network', keys: [
    ['L', 'Open the Model Lab: how the person detector was trained and tested.'],
    ['J', 'Try to beat the model on a held-out thermal image.'],
    ['I', 'Show the live counters from under the hood.'],
    ['Y', 'Show the belief map: where survivors may still be.'],
    ['W', 'Show the radio coverage the command post predicts: strong, weak or dead.'],
  ] },
]

// Keys whose data this run does not have stay out of the list: Y only when the server sends a
// belief map (maps.belief or maps.belief_command).
export function helpGroups({ belief = false } = {}) {
  return KEY_GROUPS.map((g) => ({ ...g, keys: g.keys.filter(([k]) => k !== 'Y' || belief) }))
}
