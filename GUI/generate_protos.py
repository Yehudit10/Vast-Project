from grpc_tools import protoc

protoc.main([
    'protoc',
    '-I./vast/proto',
    '--python_out=./vast/proto/generated',
    '--grpc_python_out=./vast/proto/generated',
    './vast/proto/query.proto'
])
