STDIN
"""Simple HTTP server to serve the scraper JS file"""
from http.server import HTTPServer, SimpleHTTPRequestHandler
import os

class CORSRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        return super().end_headers()

if __name__ == '__main__':
    os.chdir('/home/rajathdb/cua')
    server = HTTPServer(('localhost', 8888), CORSRequestHandler)
    print('🚀 Serving scraper at http://localhost:8888/x_post_scraper_extension.js')
    print('   Use this URL to load the scraper in your browser')
    server.serve_forever()
