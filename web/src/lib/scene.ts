import type { CameraCommand, SceneCommand } from "../types/lesson";

export interface SceneState {
  elements: SceneCommand[];
  camera: CameraCommand | undefined;
}

export const emptyScene: SceneState = { elements: [], camera: undefined };

export function applySceneCommand(scene: SceneState, command: SceneCommand): SceneState {
  if (command.kind === "clear") return { ...scene, elements: [] };
  if (command.kind === "erase") {
    return {
      ...scene,
      elements: scene.elements.filter((element) => element.id !== command.target_id),
    };
  }
  if (command.kind === "camera") return { ...scene, camera: command };
  const isAutoVisual = ["graph", "bar_chart", "venn"].includes(command.kind);
  return {
    ...scene,
    elements: [
      ...scene.elements.filter((element) => (
        element.id !== command.id &&
        (!isAutoVisual || !["graph", "bar_chart", "venn"].includes(element.kind))
      )),
      command,
    ],
  };
}
