import os
import argparse
import csv
import numpy
import matplotlib
from matplotlib import pyplot, image
import cv2
import window_dimensions
from datetime import datetime, time

##################
#     Parsing    #
##################

parser = argparse.ArgumentParser(description='Parameters required for processing.')

# required args
parser.add_argument('-i', '--input-path', type=str, default=None, required=False, help='path to the csv input')

# optional args
# parser.add_argument('-w', '--display-width', type=int, default='1400', required=False, help='width')
# parser.add_argument('-h', '--display-height', type=int, default='900', required=False, help='height')
parser.add_argument('-a', '--alpha', type=float, default='0.5', required=False, help='alpha for the gaze overlay')
parser.add_argument('-o', '--output-name', type=str, required=False, help='name for the output file')
parser.add_argument('-b', '--background-image', type=str, default=None, required=False,
                    help='path to the background image')

# advanced optional args
parser.add_argument('-n', '--n-gaussian-matrix', type=int, default='200', required=False,
                    help='width and height of gaussian matrix')
parser.add_argument('-sd', '--standard-deviation', type=float, default=None, required=False,
                    help='standard deviation of gaussian distribution')

args = vars(parser.parse_args())

# input_path = args['input-path']
# display_width = args['display-width']
# display_height = args['display-height']
alpha = args['alpha']
output_name = args['output_name'] if args['output_name'] is not None else 'output'
background_image = args['background_image']
ngaussian = args['n_gaussian_matrix']
sd = args['standard_deviation']


def gazeFileCorrection(inputfile, outfile):
    # Read Gaze file and create a new gaze files in required format
    outputFile = open(inputfile, "r")
    finalOutput = open(outfile, "w+")
    result = []
    for lines in outputFile:
        if lines == "Calibration ended\n":
            result = []
            continue
        result.append(lines)
    # finalOutput.write("time,x_gaze,y_gaze\n")
    for points in result:
        finalOutput.write(points)
    outputFile.close()
    finalOutput.close()


def is_time_between(begin_time, end_time, check_time=None):
    # If check time is not given, default to current UTC time
    check_time = check_time or datetime.utcnow().time()
    if begin_time < end_time:
        return check_time >= begin_time and check_time <= end_time
    else:  # crosses midnight
        return check_time >= begin_time or check_time <= end_time


def getStartTime(name):
    imageInfo = [word.strip() for word in name.split("_")]
    startTime = [word.strip() for word in imageInfo[2].split(".")]
    return imageInfo[1], startTime[0]


def get_output_img_size():
    dimensions = window_dimensions.get_active_window_dimensions()
    return dimensions


def draw_display(dispsize, imagefile=None):
    """Returns a matplotlib.pyplot Figure and its axes, with a size of
    dispsize, a black background colour, and optionally with an image drawn
    onto it

    arguments

    dispsize		-	tuple or list indicating the size of the display,
                    e.g. (1024,768)

    keyword arguments

    imagefile		-	full path to an image file over which the heatmap
                    is to be laid, or None for no image; NOTE: the image
                    may be smaller than the display size, the function
                    assumes that the image was presented at the centre of
                    the display (default = None)

    returns
    fig, ax		-	matplotlib.pyplot Figure and its axes: field of zeros
                    with a size of dispsize, and an image drawn onto it
                    if an imagefile was passed
    """

    # construct screen (black background)
    screen = numpy.zeros((dispsize[1], dispsize[0], 3), dtype='float32')
    # if an image location has been passed, draw the image
    if imagefile != None:
        # check if the path to the image exists
        if not os.path.isfile(imagefile):
            raise Exception("ERROR in draw_display: imagefile not found at '%s'" % imagefile)
        # load image
        img = image.imread(imagefile)

        # width and height of the image
        w, h = len(img[0]), len(img)
        # x and y position of the image on the display
        x = dispsize[0] / 2 - w / 2
        y = dispsize[1] / 2 - h / 2
        # draw the image on the screen
        screen[y:y + h, x:x + w, :] += img
    # dots per inch
    dpi = 100.0
    # determine the figure size in inches
    figsize = (dispsize[0] / dpi, dispsize[1] / dpi)
    # create a figure
    fig = pyplot.figure(figsize=figsize, dpi=dpi, frameon=False)
    ax = pyplot.Axes(fig, [0, 0, 1, 1])
    ax.set_axis_off()
    fig.add_axes(ax)
    # plot display
    ax.axis([0, dispsize[0], 0, dispsize[1]])
    ax.imshow(screen)  # , origin='upper')

    return fig, ax


def gaussian(x, sx, y=None, sy=None):
    """Returns an array of numpy arrays (a matrix) containing values between
    1 and 0 in a 2D Gaussian distribution

    arguments
    x		-- width in pixels
    sx		-- width standard deviation

    keyword argments
    y		-- height in pixels (default = x)
    sy		-- height standard deviation (default = sx)
    """

    # square Gaussian if only x values are passed
    if y == None:
        y = x
    if sy == None:
        sy = sx
    # centers
    xo = x / 2
    yo = y / 2
    # matrix of zeros
    M = numpy.zeros([y, x], dtype=float)
    # gaussian matrix
    for i in range(x):
        for j in range(y):
            M[j, i] = numpy.exp(
                -1.0 * (((float(i) - xo) ** 2 / (2 * sx * sx)) + ((float(j) - yo) ** 2 / (2 * sy * sy))))

    return M


def draw_heatmap(gazepoints, dispsize, imagefile=None, alpha=0.5, savefilename=None, gaussianwh=200, gaussiansd=None):
    """Draws a heatmap of the provided fixations, optionally drawn over an
    image, and optionally allocating more weight to fixations with a higher
    duration.

    arguments

    gazepoints		-	a list of gazepoint tuples (x, y)

    dispsize		-	tuple or list indicating the size of the display,
                    e.g. (1024,768)

    keyword arguments

    imagefile		-	full path to an image file over which the heatmap
                    is to be laid, or None for no image; NOTE: the image
                    may be smaller than the display size, the function
                    assumes that the image was presented at the centre of
                    the display (default = None)
    alpha		-	float between 0 and 1, indicating the transparancy of
                    the heatmap, where 0 is completely transparant and 1
                    is completely untransparant (default = 0.5)
    savefilename	-	full path to the file in which the heatmap should be
                    saved, or None to not save the file (default = None)

    returns

    fig			-	a matplotlib.pyplot Figure instance, containing the
                    heatmap
    """

    # IMAGE
    fig, ax = draw_display(dispsize, imagefile=imagefile)

    # HEATMAP
    # Gaussian
    gwh = gaussianwh
    gsdwh = gwh / 6 if (gaussiansd is None) else gaussiansd
    gaus = gaussian(gwh, gsdwh)
    # matrix of zeroes
    strt = gwh / 2
    heatmapsize = dispsize[1] + 2 * int(strt), dispsize[0] + 2 * int(strt)
    print(heatmapsize)
    heatmap = numpy.zeros(heatmapsize, dtype=float)
    # create heatmap
    for i in range(0, len(gazepoints)):
        # get x and y coordinates
        x = strt + gazepoints[i][0] - int(gwh / 2)
        y = strt + gazepoints[i][1] - int(gwh / 2)
        # correct Gaussian size if either coordinate falls outside of
        # display boundaries
        if (not 0 < x < dispsize[0]) or (not 0 < y < dispsize[1]):
            hadj = [0, gwh];
            vadj = [0, gwh]
            if 0 > x:
                hadj[0] = abs(x)
                x = 0
            elif dispsize[0] < x:
                hadj[1] = gwh - int(x - dispsize[0])
            if 0 > y:
                vadj[0] = abs(y)
                y = 0
            elif dispsize[1] < y:
                vadj[1] = gwh - int(y - dispsize[1])
            # add adjusted Gaussian to the current heatmap
            try:
                heatmap[y:y + vadj[1], x:x + hadj[1]] += gaus[vadj[0]:vadj[1], hadj[0]:hadj[1]] * gazepoints[i][2]
            except:
                # fixation was probably outside of display
                pass
        else:
            # add Gaussian to the current heatmap
            heatmap[int(y):int(y + gwh), int(x):int(x + gwh)] += gaus * gazepoints[i][2]
    # resize heatmap
    heatmap = heatmap[int(strt):int(dispsize[1] + strt), int(strt):int(dispsize[0] + strt)]
    # remove zeros
    lowbound = numpy.mean(heatmap[heatmap > 0])  # + 100
    # print(lowbound,len(heatmap))
    heatmap[heatmap < lowbound] = numpy.NaN
    # draw heatmap on top of image
    ax.imshow(heatmap, cmap='jet', alpha=alpha)

    # FINISH PLOT
    # invert the y axis, as (0,0) is top left on a display
    ax.invert_yaxis()
    # save the figure if a file name was provided
    if savefilename is not None:
        fig.savefig(savefilename)

    return fig


def bounding_box(imageName, FrameName):
    image = cv2.imread(imageName)
    roi_copy = image.copy()
    roi_hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)

    # ## mask of green (36,0,0) ~ (70, 255,255)
    # mask1 = cv2.inRange(hsv, (36, 0, 0), (70, 255,255))

    # ## mask o yellow (15,0,0) ~ (36, 255, 255)
    # mask2 = cv2.inRange(hsv, (15,0,0), (36, 255, 255))

    # filter black color
    # mask1 = cv2.inRange(roi_hsv, numpy.array([0, 0, 0]), numpy.array([180, 255, 125]))
    mask1 = cv2.inRange(roi_hsv, numpy.array([0, 0, 0]), numpy.array([70, 255, 255]))
    mask1 = cv2.morphologyEx(mask1, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    mask1 = cv2.Canny(mask1, 100, 300)
    mask1 = cv2.GaussianBlur(mask1, (1, 1), 0)
    mask1 = cv2.Canny(mask1, 100, 300)

    # find contours
    # cv2.findCountours() function changed from OpenCV3 to OpenCV4: now it have only two parameters instead of 3
    cv2MajorVersion = cv2.__version__.split(".")[0]
    # check for contours on thresh
    if int(cv2MajorVersion) >= 4:
        ctrs, hier = cv2.findContours(mask1.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    else:
        im2, ctrs, hier = cv2.findContours(mask1.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    bbox_file = open("bbox_points.txt", "a")
    bbox_file.write(FrameName + " | ")
    # sort contours
    sorted_ctrs = sorted(ctrs, key=lambda ctr: cv2.boundingRect(ctr)[0])
    for i, ctr in enumerate(sorted_ctrs):
        if cv2.contourArea(ctr) > 50:
            peri = cv2.arcLength(ctr, True)
            approx = cv2.approxPolyDP(ctr, 0.02 * peri, True)
            x, y, w, h = cv2.boundingRect(approx)
            print(x, y, cv2.contourArea(ctr))

            # Get bounding box
            # x, y, w, h = cv2.boundingRect(ctr)

            # Getting ROI
            roi = image[y:y + h, x:x + w]
            # show ROI
            # cv2.imshow('segment no:'+str(i),roi)
            # cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)
            if w > 15 and h > 15:
                # cv2.imwrite('out_check_out.png'.format(i), roi)
                cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)
                bbox_file.write(str(x) + " " + str(y) + " " + str(w) + " " + str(h) + " " + " | ")

    bbox_file.write("\n")
    bbox_file.close()
    # cv2.imshow('marked areas', image)
    # cv2.imwrite('out_check_out.png', image)
    # cv2.waitKey(0)


def GazeFrameMap(coordinatesFileName):
    frameDict = {}
    frameNum = []
    imageNames = os.listdir("../text_extraction/Frames/")
    for frames in imageNames:
        frame_number, startTime = getStartTime(frames)
        frameNum.append(int(frame_number))
        frameDict[int(frame_number)] = startTime
    frameNum.sort()
    lastFrame = frameNum[-1]
    for frameName in imageNames:
        gazePoints = []
        frame_number, startTime = getStartTime(frameName)
        if int(frame_number) == lastFrame:
            continue
        endTime = frameDict[int(frame_number) + 1]
        file = open(coordinatesFileName, "r")
        for lines in file:
            gazeInfo = [word.strip() for word in lines.split(',')]
            if is_time_between(startTime, endTime, gazeInfo[2]):
                gazePoints.append([int(gazeInfo[0]), int(gazeInfo[1]), 1])  # , gazeInfo[2]))

        # Pass the gazepoints and the frameName to the heat map generator.
        print(gazePoints)
        HeatMap_OutFile = frameName[0:-4]+"_out.png"
        dimFile = open("Window_dim.txt", "r")
        out_dimensions = dimFile.read().split(" ")
        # out_dimensions = get_output_img_size()
        display_width = int(out_dimensions[0])
        display_height = int(out_dimensions[1])
        print(display_width, display_height)
        draw_heatmap(gazePoints, (display_width, display_height), alpha=alpha,
                                       savefilename=HeatMap_OutFile,
                                       imagefile=background_image, gaussianwh=ngaussian, gaussiansd=sd)

        bounding_box(HeatMap_OutFile, frameName)


# Main Function to call all the other function.

InputGazeFile = "../OpenGazer/gaze_points.csv"
OutputGazeFile = "FinalGaze.csv"
gazeFileCorrection(InputGazeFile, OutputGazeFile)
GazeFrameMap(OutputGazeFile)
