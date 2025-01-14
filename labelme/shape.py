import copy
from labelme.logger import logger
import math

from qtpy import QtCore
from qtpy import QtGui
import numpy as np
import labelme.utils
import time

# TODO(unknown):
# - [opt] Store paths instead of creating new ones at each paint.


DEFAULT_LINE_COLOR = QtGui.QColor(0, 255, 0, 128)  # bf hovering
DEFAULT_FILL_COLOR = QtGui.QColor(0, 255, 0, 128)  # hovering
DEFAULT_SELECT_LINE_COLOR = QtGui.QColor(255, 255, 255)  # selected
DEFAULT_SELECT_FILL_COLOR = QtGui.QColor(0, 255, 0, 155)  # selected
DEFAULT_VERTEX_FILL_COLOR = QtGui.QColor(0, 255, 0, 255)  # hovering
DEFAULT_HVERTEX_FILL_COLOR = QtGui.QColor(255, 255, 255, 255)  # hovering


class Shape(object):

    # Render handles as squares
    P_SQUARE = 0

    # Render handles as circles
    P_ROUND = 1

    # Flag for the handles we would move if dragging
    MOVE_VERTEX = 0

    # Flag for all other handles on the curent shape
    NEAR_VERTEX = 1

    # The following class variables influence the drawing of all shape objects.
    line_color = DEFAULT_LINE_COLOR
    fill_color = DEFAULT_FILL_COLOR
    select_line_color = DEFAULT_SELECT_LINE_COLOR
    select_fill_color = DEFAULT_SELECT_FILL_COLOR
    vertex_fill_color = DEFAULT_VERTEX_FILL_COLOR
    hvertex_fill_color = DEFAULT_HVERTEX_FILL_COLOR
    point_type = P_ROUND
    point_size = 8
    scale = 1.0

    def __init__(
        self,
        label=None,
        line_color=None,
        shape_type=None,
        flags={},
        group_id=None,
        vertex_epsilon=None
    ):
        self.label = label
        self.group_id = group_id
        self.points = []
        self.fill = False
        self.selected = False
        self.shape_type = shape_type
        self.flags = flags
        self.poly = None
        self.other_data = {}
        self.vertex_epsilon = vertex_epsilon
        self.prev_val = None
        self.poly_array = None

        self._highlightIndex = None
        self._highlightMode = self.NEAR_VERTEX
        self._highlightSettings = {
            self.NEAR_VERTEX: (5, self.P_ROUND),
            self.MOVE_VERTEX: (4, self.P_SQUARE),
        }

        self._closed = False

        if line_color is not None:
            # Override the class line_color attribute
            # with an object attribute. Currently this
            # is used for drawing the pending line a different color.
            self.line_color = line_color

        self.shape_type = shape_type

    @property
    def shape_type(self):
        return self._shape_type

    @shape_type.setter
    def shape_type(self, value):
        if value is None:
            value = "polygon"
        if value not in [
            "polygon",
            "trace",
            "rectangle",
            "point",
            "line",
            "circle",
            "linestrip",
        ]:
            raise ValueError("Unexpected shape_type: {}".format(value))
        self._shape_type = value

    def close(self):
        self._closed = True

    def addPoint(self, point):
        if self.points and point == self.points[0]:
            self.close()
        else:
            self.points.append(point)
            if self.poly_array is None:
                self.init_poly_array()
                # import IPython; IPython.embed()
                return
            
            self.poly_array = np.append(self.poly_array, [[point.x(), point.y()]], axis=0)

    def canAddPoint(self):
        return self.shape_type in ["polygon", "trace", "linestrip"]

    def popPoint(self):
        if self.points:
            self.poly_array = self.poly_array[:-1]
            return self.points.pop()
        return None

    def insertPoint(self, i, point):
        self.points.insert(i, point)
        np.insert(self.poly_array, i, np.array([point.x(), point.y()]))

    def removePoint(self, i):
        try:
            self.points.pop(i)
            self.poly_array = np.delete(self.poly_array, i, axis=0)
        except IndexError:
            logger.warn(f"Index Error with point {i}")
            pass

    def isClosed(self):
        return self._closed

    def setOpen(self):
        self._closed = False

    def getRectFromLine(self, pt1, pt2):
        x1, y1 = pt1.x(), pt1.y()
        x2, y2 = pt2.x(), pt2.y()
        return QtCore.QRectF(x1, y1, x2 - x1, y2 - y1)

    def paint(self, painter):
        if self.points:
            color = (
                self.select_line_color if self.selected else self.line_color
            )
            pen = QtGui.QPen(color)
            # Try using integer sizes for smoother drawing(?)
            pen.setWidth(max(1, int(round(2.0 / self.scale))))
            painter.setPen(pen)

            line_path = QtGui.QPainterPath()
            vrtx_path = QtGui.QPainterPath()

            if self.shape_type == "rectangle":
                assert len(self.points) in [1, 2]
                if len(self.points) == 2:
                    rectangle = self.getRectFromLine(*self.points)
                    line_path.addRect(rectangle)
                for i in range(len(self.points)):
                    self.drawVertex(vrtx_path, i)
            elif self.shape_type == "circle":
                assert len(self.points) in [1, 2]
                if len(self.points) == 2:
                    rectangle = self.getCircleRectFromLine(self.points)
                    line_path.addEllipse(rectangle)
                for i in range(len(self.points)):
                    self.drawVertex(vrtx_path, i)
            elif self.shape_type == "linestrip":
                line_path.moveTo(self.points[0])
                for i, p in enumerate(self.points):
                    line_path.lineTo(p)
                    self.drawVertex(vrtx_path, i)
            else:
                line_path.moveTo(self.points[0])
                # self.poly = QtGui.QPolygonF(self.points)
                self.init_poly_array()
                self.x_span = np.max(self.poly_array[:, 0]) -\
                    np.min(self.poly_array[:, 0])
                self.y_span = np.max(self.poly_array[:, 1]) -\
                    np.min(self.poly_array[:, 1])
                # self.onPolygonChange()
                # Uncommenting the following line will draw 2 paths
                # for the 1st vertex, and make it non-filled, which
                # may be desirable.
                # self.drawVertex(vrtx_path, 0)

                for i, p in enumerate(self.points):
                    line_path.lineTo(p)
                    self.drawVertex(vrtx_path, i)
                if self.isClosed():
                    line_path.lineTo(self.points[0])

            painter.drawPath(line_path)
            painter.drawPath(vrtx_path)
            painter.fillPath(vrtx_path, self._vertex_fill_color)
            if self.fill:
                color = (
                    self.select_fill_color
                    if self.selected
                    else self.fill_color
                )
                painter.fillPath(line_path, color)

    def drawVertex(self, path, i):
        d = self.point_size / (self.scale * 2)
        shape = self.point_type
        point = self.points[i]
        if i == self._highlightIndex:
            size, shape = self._highlightSettings[self._highlightMode]
            try:
                d *= size
            except TypeError:
                logger.info("highlighting the vertecies,\
                    wasnt able to keep up with cursor")
                pass
        if self._highlightIndex is not None:
            self._vertex_fill_color = self.hvertex_fill_color
        else:
            self._vertex_fill_color = self.vertex_fill_color
        if shape == self.P_SQUARE:
            path.addRect(point.x() - d / 2, point.y() - d / 2, d, d)
        elif shape == self.P_ROUND:
            path.addEllipse(point, d, d)
        else:
            assert False, "unsupported vertex shape"

    def nearestVertex(self, point, epsilon):
        self.component_dist = self.poly_array - np.array([point.x(),
                                                          point.y()])
        dist = np.sum((self.component_dist)**2, axis=1)
        if np.sqrt(np.min(dist)) < epsilon:
            return np.argmin(dist), None
        else:
            return None, np.argmin(dist)

    def nearestEdge(self, point, epsilon, minDistIndex=None):

        # TODO further optimize the algorightm, maybe preselect
        # those which are closer than y_span/2 or x_span/2
        self.t = time.time()
        if (np.abs(self.t - np.round(self.t)) <= 0.005) and\
                self.prev_val is not None:
            return self.prev_val

        lenght = len(self.poly_array)
        for i, j in zip(range(
                minDistIndex,
                minDistIndex + int(lenght / 2)),
                range(minDistIndex, minDistIndex - int(lenght / 2), -1)):

            if i == 0:
                line_pos = np.array([self.poly_array[-1], self.poly_array[0]])
            elif i == lenght:
                line_pos = np.array([self.poly_array[-1], self.poly_array[0]])
            else:
                i = i % lenght
                line_pos = self.poly_array[i - 1:i + 1]
            if j > 0 or j < -1:
                line_neg = self.poly_array[j - 1:j + 1]
            elif j == 0:
                line_neg = np.array([self.poly_array[-1], self.poly_array[0]])
            elif j == -1:
                line_neg = self.poly_array[:2]

            dist_i, dist_j = [labelme.utils.distancetoline(point, line)
                              for line in [line_pos, line_neg]]
            if dist_i <= epsilon:
                self.prev_val = i
                return i
            elif dist_j <= epsilon:
                self.prev_val = i
                return j

        return None

    def containsPoint(self, point):
        return self.makePath().contains(point)

    def getCircleRectFromLine(self, line):
        """Computes parameters to draw with `QPainterPath::addEllipse`"""
        if len(line) != 2:
            return None
        (c, point) = line
        r = line[0] - line[1]
        d = math.sqrt(math.pow(r.x(), 2) + math.pow(r.y(), 2))
        rectangle = QtCore.QRectF(c.x() - d, c.y() - d, 2 * d, 2 * d)
        return rectangle

    def makePath(self):
        if self.shape_type == "rectangle":
            path = QtGui.QPainterPath()
            if len(self.points) == 2:
                rectangle = self.getRectFromLine(*self.points)
                path.addRect(rectangle)
        elif self.shape_type == "circle":
            path = QtGui.QPainterPath()
            if len(self.points) == 2:
                rectangle = self.getCircleRectFromLine(self.points)
                path.addEllipse(rectangle)
        else:
            path = QtGui.QPainterPath(self.points[0])
            for p in self.points[1:]:
                path.lineTo(p)
        return path

    def boundingRect(self):
        return self.makePath().boundingRect()

    def moveBy(self, offset):
        self.points = [p + offset for p in self.points]
        self.poly_array = self.poly_array + np.array([offset.x(), offset.y()])

    def moveVertexBy(self, i, offset):
        self.points[i] = self.points[i] + offset
        self.poly_array[i] = self.poly_array[i] + np.array([offset.x(),
                                                            offset.y()])

    def highlightVertex(self, i, action):
        """Highlight a vertex appropriately based on the current action

        Args:
            i (int): The vertex index
            action (int): The action
            (see Shape.NEAR_VERTEX and Shape.MOVE_VERTEX)
        """
        self._highlightIndex = i
        self._highlightMode = action

    def init_poly_array(self):
        self.poly_array = np.array([[p.x(), p.y()]
                                            for p in self.points])

    def highlightClear(self):
        """Clear the highlighted point"""
        self._highlightIndex = None

    def copy(self):
        return copy.deepcopy(self)

    def __len__(self):
        return len(self.points)

    def __getitem__(self, key):
        return self.points[key]

    def __setitem__(self, key, value):
        self.points[key] = value
