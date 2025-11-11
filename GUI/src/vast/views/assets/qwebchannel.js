/****************************************************************************
**
**  qwebchannel.js — Official Qt WebChannel client
**  Enables communication between QWebEngineView (Python) and JavaScript.
**
****************************************************************************/

(function() {
"use strict";

var QWebChannelMessageTypes = {
    signal: 1,
    propertyUpdate: 2,
    init: 3,
    idle: 4,
    debug: 5,
    invokeMethod: 6,
    connectToSignal: 7,
    disconnectFromSignal: 8,
    setProperty: 9,
    response: 10
};

function QObject(name, data, transport) {
    this.__id__ = name;
    this.__objectSignals__ = {};
    this.__transport__ = transport;

    for (var prop in data.methods) {
        (function(methodIdx) {
            var methodData = data.methods[methodIdx];
            this[methodData[0]] = function() {
                var args = [];
                for (var i = 0; i < arguments.length; ++i)
                    args.push(arguments[i]);
                this.__invokeMethod__(methodIdx, args);
            }.bind(this);
        }).call(this, prop);
    }

    for (var prop in data.properties) {
        (function(propertyIdx) {
            var propertyData = data.properties[propertyIdx];
            var propertyName = propertyData[0];
            var value = propertyData[1];
            Object.defineProperty(this, propertyName, {
                configurable: true,
                enumerable: true,
                get: function() { return value; },
                set: function(newValue) {
                    value = newValue;
                    this.__setProperty__(propertyIdx, newValue);
                }.bind(this)
            });
        }).call(this, prop);
    }

    for (var prop in data.signals) {
        (function(signalIdx) {
            var signalData = data.signals[signalIdx];
            var signalName = signalData[0];
            this[signalName] = {
                connect: function(callback) {
                    if (typeof callback !== "function") return;
                    this.__connectToSignal__(signalIdx, callback);
                }.bind(this),
                disconnect: function(callback) {
                    this.__disconnectFromSignal__(signalIdx, callback);
                }.bind(this)
            };
        }).call(this, prop);
    }
}

QObject.prototype.__invokeMethod__ = function(methodIdx, args) {
    this.__transport__.send(JSON.stringify({
        type: QWebChannelMessageTypes.invokeMethod,
        object: this.__id__,
        method: methodIdx,
        args: args
    }));
};

QObject.prototype.__setProperty__ = function(propertyIdx, value) {
    this.__transport__.send(JSON.stringify({
        type: QWebChannelMessageTypes.setProperty,
        object: this.__id__,
        property: propertyIdx,
        value: value
    }));
};

QObject.prototype.__connectToSignal__ = function(signalIdx, callback) {
    if (!this.__objectSignals__[signalIdx])
        this.__objectSignals__[signalIdx] = [];
    this.__objectSignals__[signalIdx].push(callback);

    this.__transport__.send(JSON.stringify({
        type: QWebChannelMessageTypes.connectToSignal,
        object: this.__id__,
        signal: signalIdx
    }));
};

QObject.prototype.__disconnectFromSignal__ = function(signalIdx, callback) {
    var handlers = this.__objectSignals__[signalIdx];
    if (!handlers) return;
    var idx = handlers.indexOf(callback);
    if (idx >= 0)
        handlers.splice(idx, 1);
    if (handlers.length === 0) {
        delete this.__objectSignals__[signalIdx];
        this.__transport__.send(JSON.stringify({
            type: QWebChannelMessageTypes.disconnectFromSignal,
            object: this.__id__,
            signal: signalIdx
        }));
    }
};

QObject.prototype.__signalEmitted__ = function(signalName, args) {
    var handlers = this.__objectSignals__[signalName];
    if (handlers) {
        handlers.forEach(function(cb) { cb.apply(null, args); });
    }
};

function QWebChannel(transport, initCallback) {
    this.transport = transport;
    this.objects = {};

    var channel = this;
    this.transport.onmessage = function(message) {
        var data = JSON.parse(message.data);
        switch (data.type) {
        case QWebChannelMessageTypes.init:
            Object.keys(data.data).forEach(function(name) {
                channel.objects[name] = new QObject(name, data.data[name], transport);
            });
            if (initCallback)
                initCallback(channel);
            break;
        case QWebChannelMessageTypes.signal:
            var object = channel.objects[data.object];
            if (object)
                object.__signalEmitted__(data.signal, data.args);
            break;
        case QWebChannelMessageTypes.propertyUpdate:
            Object.keys(data.data).forEach(function(objName) {
                var obj = channel.objects[objName];
                var props = data.data[objName];
                Object.keys(props).forEach(function(propName) {
                    obj[propName] = props[propName];
                });
            });
            break;
        case QWebChannelMessageTypes.response:
            break;
        }
    };

    this.exec = function(data) {
        this.transport.send(JSON.stringify(data));
    };
}

// Export
if (typeof module !== "undefined" && module.exports) {
    module.exports = QWebChannel;
} else {
    window.QWebChannel = QWebChannel;
}
})();
