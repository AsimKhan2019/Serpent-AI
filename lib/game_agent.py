import offshoot

from lib.config import config

import time
import uuid
import pickle

import os
import os.path

import lib.ocr

from lib.game_frame_buffer import GameFrameBuffer
from lib.sprite_identifier import SpriteIdentifier
from lib.visual_debugger.visual_debugger import VisualDebugger

import skimage.io
import skimage.transform

from redis import StrictRedis

from datetime import datetime


class GameAgentError(BaseException):
    pass


class GameAgent(offshoot.Pluggable):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.game = kwargs["game"]
        self.config = config.get(f"{self.__class__.__name__}Plugin")

        self.redis_client = StrictRedis(**config["redis"])

        self.input_controller = kwargs["input_controller"]
        self.machine_learning_models = dict()

        self.frame_handlers = dict(
            NOOP=self.handle_noop,
            COLLECT_FRAMES=self.handle_collect_frames,
            COLLECT_FRAMES_FOR_CONTEXT=self.handle_collect_frames_for_context,
            COLLECT_CHARACTERS=self.handle_collect_characters
        )

        self.frame_handler_setups = dict(
            COLLECT_FRAMES_FOR_CONTEXT=self.setup_collect_frames_for_context
        )

        self.frame_handler_setup_performed = False

        self.visual_debugger = VisualDebugger()

        self.game_frame_buffer = GameFrameBuffer(size=self.config.get("game_frame_buffer_size", 5))
        self.game_context = None

        self.sprite_identifier = SpriteIdentifier()
        self._register_sprites()

        self.flag = None

        self.uuid = str(uuid.uuid4())
        self.started_at = datetime.now()

    @offshoot.forbidden
    def on_game_frame(self, game_frame):
        if not self.frame_handler_setup_performed:
            self._setup_frame_handler()

        frame_handler = self.frame_handlers.get(self.config.get("frame_handler", "NOOP"))

        frame_handler(game_frame)

        self.game_frame_buffer.add_game_frame(game_frame)

    @offshoot.forbidden
    def load_machine_learning_model(self, file_path):
        with open(file_path, "rb") as f:
            serialized_classifier = f.read()

        return pickle.loads(serialized_classifier)

    def handle_noop(self, frame):
        time.sleep(1)

    def setup_collect_frames_for_context(self):
        context = config["frame_handlers"]["COLLECT_FRAMES_FOR_CONTEXT"]["context"]

        if not os.path.isdir(f"datasets/collect_frames_for_context/{context}"):
            os.mkdir(f"datasets/collect_frames_for_context/{context}")

    def handle_collect_frames(self, game_frame):
        skimage.io.imsave(f"datasets/collect_frames/frame_{str(uuid.uuid4())}.png", game_frame.frame)
        time.sleep(self.config.get("collect_frames_interval") or 1)

    def handle_collect_frames_for_context(self, game_frame):
        context = config["frame_handlers"]["COLLECT_FRAMES_FOR_CONTEXT"]["context"]
        interval = config["frame_handlers"]["COLLECT_FRAMES_FOR_CONTEXT"]["interval"]

        resized_frame = skimage.transform.resize(
            game_frame.frame,
            (game_frame.frame.shape[0] // 2, game_frame.frame.shape[1] // 2)
        )

        file_name = f"datasets/collect_frames_for_context/{context}/frame_{str(uuid.uuid4())}.png"
        skimage.io.imsave(file_name, resized_frame)

        time.sleep(interval)

    def handle_collect_characters(self, game_frame):
        frame_uuid = str(uuid.uuid4())

        skimage.io.imsave(f"datasets/ocr/frames/frame_{frame_uuid}.png", game_frame.frame)

        lib.ocr.prepare_dataset_tokens(game_frame.frame, frame_uuid)

        time.sleep(self.config.get("collect_character_interval") or 1)

    def _setup_frame_handler(self):
        if self.config.get("frame_handler", "NOOP") in self.frame_handler_setups:
            self.frame_handler_setups[self.config.get("frame_handler", "NOOP")]()

        self.frame_handler_setup_performed = True

    def _register_sprites(self):
        for sprite_name, sprite in self.game.sprites.items():
            self.sprite_identifier.register(sprite)
