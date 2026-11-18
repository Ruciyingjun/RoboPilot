"""Read-only live Web Viewer for the ROS-owned simulation (MuJoCo 4.0)."""

from mujoco.studio import app, launch_web, messages, plugin, viewer_protocol


class _RosOwnsPhysics(plugin.SimPlugin):
    # The ROS bridge owns clock, model topology, controls and physics. Browser
    # reset/state edits would otherwise bypass that contract or rewind /clock.
    @messages.handler(priority=messages.Priority.CRITICAL)
    def block_edits(self, message: messages.Message):
        return isinstance(message, (
            messages.LoadModelEvent, messages.StateEvent, messages.PerturbSnapshot,
            messages.ResetEvent, messages.MjOptionSnapshot, messages.KeyframeEvent,
            messages.ThreadPoolEvent, messages.StepControlSnapshot,
        ))


class LiveViewer:
    def __init__(self, model, data, port):
        self.handle = launch_web.launch(viewer_protocol.ViewerConfig(
            title='RoboPilot ROS live view', gfx='web', http_port=port,
            open_browser=False), plugins=[app.App(), _RosOwnsPhysics()])
        self.handle.set_model(model, data=data)

    def sync(self):
        if not self.handle.is_running():
            raise RuntimeError('MuJoCo Web Viewer stopped; restart the bridge')
        # No StepControl plugin: sync sends snapshots, never advances physics.
        self.handle.sync()

    def close(self):
        self.handle.close()
