var webpack = require('webpack');
var ExtractTextPlugin = require('extract-text-webpack-plugin');
var pkg = require('./package.json');

var bundleCss = 'css/main.css';
var pluginsWebpack = [
    new ExtractTextPlugin(bundleCss),
];

module.exports = {
    entry: './js/editor.js',
    output: {
        path: __dirname + '/resources',
        filename: 'bundle.js'
    },
    module: {
        rules: [
            {
                test: /\.js?$/,
                use: [{
                    loader: 'babel-loader'
                }],
                exclude: /node_modules/
            },
            {
                test: /\.sass$/,
                use: ExtractTextPlugin.extract({
                  fallback: 'style-loader',
                  use: ['css-loader', 'sass-loader']
                })
            }
        ]
    },
    plugins: pluginsWebpack
};
