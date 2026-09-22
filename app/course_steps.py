from enum import IntEnum


class CourseStep(IntEnum):
    REGISTERED = 0
    INTRO = 1
    FIGMA_CHOICE = 2
    READY = 3
    LESSON_1 = 4
    LESSON_1_DONE = 5
    LESSON_2 = 6
    TEST_2_ACTIVE = 7
    TEST_2_DONE = 8
    LESSON_3 = 9
    LESSON_3_DONE = 10
    SURVEY = 11
    COMPLETED = 12
